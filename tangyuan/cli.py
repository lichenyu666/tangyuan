from __future__ import annotations

import json
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from tangyuan import __version__
from tangyuan.agent import TangyuanAgent
from tangyuan.config import load_settings
from tangyuan.skills import list_skills
from tangyuan.memory import (
    daily_log_path,
    ensure_default_user_memory,
    global_memory_dir,
    history_path,
    memory_md_path,
    project_memory_path,
    read_long_term_memory,
    summarize_tokens,
    tokens_path,
    write_memory,
)
from tangyuan.tools import build_default_tools
from tangyuan.trace import TraceLogger

app = typer.Typer(
    add_completion=False,
    invoke_without_command=True,
    help="汤圆 Tangyuan — 李晨雨独立实现的终端 Agent",
)
console = Console()


def _confirm(title: str, detail: str) -> bool:
    console.print(Panel(detail, title=f"[yellow]{title}[/yellow]", border_style="yellow"))
    return typer.confirm("确认执行？", default=False)


def _on_event(kind: str, **payload) -> None:
    if kind == "step":
        console.print(f"[dim]── step {payload['step']}/{payload['max_steps']} ──[/dim]")
    elif kind == "assistant_delta":
        console.print(f"[blue]{payload.get('content')}[/blue]")
    elif kind == "tool_call":
        args = json.dumps(payload["args"], ensure_ascii=False)
        if len(args) > 120:
            args = args[:120] + "..."
        console.print(f"  [magenta]⚙ {payload['name']}[/magenta] {args}")
    elif kind == "tool_result":
        preview = str(payload.get("result", "")).replace("\n", " ")
        if len(preview) > 160:
            preview = preview[:160] + "..."
        console.print(f"  [green]✓[/green] {preview}")
    elif kind == "plan":
        items = payload.get("items") or []
        if not items:
            console.print("[dim]📋 计划已清空[/dim]")
            return
        console.print("[cyan]📋 任务计划[/cyan]")
        marks = {
            "pending": "[ ]",
            "in_progress": "[>]",
            "completed": "[x]",
            "cancelled": "[-]",
        }
        for it in items:
            mark = marks.get(it.get("status"), "[ ]")
            console.print(
                f"  {mark} {it.get('id')}: {it.get('content')} "
                f"[dim]({it.get('status')})[/dim]"
            )
    elif kind == "plan_stall":
        if payload.get("gate"):
            console.print(
                "[yellow]⚠ 计划未办妥，已拦截收工并催促继续（Stop Gate）[/yellow]"
            )
        else:
            console.print(
                "[yellow]⚠ 未完成项多步无进展，已提醒核对计划并回退换路径[/yellow]"
            )
    elif kind == "subagent":
        console.print(
            f"[cyan]♟ 子代理回禀[/cyan] {payload.get('preview', '')}"
        )
    elif kind == "spin":
        console.print(
            "[yellow]⚠ 检测到重复调用，已提醒换路径（避免空转）[/yellow]"
        )
    elif kind == "final":
        console.print()
        console.print(Panel(payload.get("content") or "(空)", title="汤圆", border_style="green"))
    elif kind == "compact":
        console.print(
            f"[dim]↻ 会话已压缩：归档 {payload.get('old')} 条，保留最近 {payload.get('kept')} 条[/dim]"
        )
    elif kind == "distill":
        items = payload.get("items") or []
        if items:
            console.print(f"[dim]📝 已蒸馏项目记忆 {len(items)} 条[/dim]")


def _banner(settings, ws) -> None:
    tools = build_default_tools(ws)
    console.print(
        Panel(
            f"[bold]汤圆 Tangyuan[/bold] v{__version__}\n"
            f"model     : {settings.model}\n"
            f"workspace : {ws}\n"
            f"tools     : {', '.join(tools.names())}\n\n"
            "[dim]直接输入需求。拖文件到终端或写 @路径 可附带文件。\n"
            "复杂任务：update_plan 收口；子代理 / Team / MCP(time) 已接入。\n"
            "长期记忆：/remember  |  /memory  |  /tokens\n"
            "命令: /help  /tools  /skills  /skill  /team  /inbox  /memory  /remember  /tokens  /clear  /exit[/dim]",
            border_style="blue",
            title="对话框已就绪",
        )
    )


def _print_skills(ws) -> None:
    skills = list_skills(ws)
    if not skills:
        console.print("[yellow]还没有 skills/*/SKILL.md[/yellow]")
        return
    table = Table(title="可用 Skills（渐进披露：摘要先见，全文按需 load）")
    table.add_column("id", style="cyan")
    table.add_column("标题")
    table.add_column("何时使用")
    for s in skills:
        table.add_row(s["id"], s["title"], s.get("when", "")[:60])
    console.print(table)
    console.print("[dim]默认：摘要进系统提示，匹配后 load_skill；/skill <id> 强制全文；/skill off 取消[/dim]")


def _make_agent(settings, yes: bool, forced_skill_id: Optional[str] = None) -> TangyuanAgent:
    ws = settings.resolve_workspace()
    if yes:
        confirm = None
        confirm_writes = False
        confirm_shell = False
    else:
        confirm = _confirm
        confirm_writes = settings.confirm_writes
        confirm_shell = settings.require_confirm_shell
    tools = build_default_tools(
        ws,
        settings.shell_timeout,
        confirm=confirm,
        confirm_writes=confirm_writes,
        confirm_shell=confirm_shell,
        settings=settings,
    )
    trace = TraceLogger(ws)
    return TangyuanAgent(
        settings, tools, trace, on_event=_on_event, forced_skill_id=forced_skill_id
    )


def _maybe_distill(agent: TangyuanAgent, label: str) -> None:
    try:
        written = agent.distill_project_memory()
    except Exception as e:  # noqa: BLE001
        console.print(f"[dim]蒸馏跳过：{e}[/dim]")
        return
    if written:
        console.print(f"[dim]📝 {label}：已写入 {len(written)} 条项目记忆[/dim]")


def interactive(
    workspace: Optional[str] = None,
    model: Optional[str] = None,
    yes: bool = False,
) -> None:
    """Claude Code 风格：进入终端对话框。"""
    settings = load_settings(workspace=workspace, model=model)
    ws = settings.resolve_workspace()
    _banner(settings, ws)
    agent = _make_agent(settings, yes=yes)

    while True:
        try:
            line = console.input("[bold cyan]你 ›[/bold cyan] ").strip()
        except (EOFError, KeyboardInterrupt):
            _maybe_distill(agent, "退出前")
            console.print("\n[dim]再见。[/dim]")
            break

        if not line:
            continue
        if line in {"/exit", "/quit", "exit", "quit"}:
            _maybe_distill(agent, "退出前")
            console.print("[dim]再见。[/dim]")
            break
        if line in {"/help", "help"}:
            console.print(
                Panel(
                    "直接说需求即可（Skills 会按意图自动选用），例如：\n"
                    "• 帮我搜一下 LangGraph，并打开官方文档\n"
                    "• 这个仓库是干什么的\n"
                    "• @README.md 根据它做个 3 页 PPT\n"
                    "• 这段报错怎么修：（粘贴日志）\n\n"
                    "复杂任务：update_plan 拆步骤并收口；细节用子代理；长期协作用 Team。\n\n"
                    "手动 Skill：\n"
                    "/skills           列出技能\n"
                    "/skill fix-error  强制用「修报错」剧本\n"
                    "/skill off        取消强制，改回自动\n\n"
                    "Team：\n"
                    "/team             查看队友状态\n"
                    "/inbox            读取 lead inbox\n\n"
                    "长期记忆（分层）：\n"
                    "/remember topic:姓名 李晨雨\n"
                    "/remember project 本仓库用 DeepSeek\n"
                    "/memory           查看 MEMORY / 日记 / 路径\n"
                    "/tokens           查看 Token 用量汇总\n\n"
                    "/tools  /clear  /exit",
                    title="帮助",
                )
            )
            continue
        if line == "/tools":
            list_tools()
            continue
        if line == "/skills":
            _print_skills(ws)
            continue
        if line.startswith("/skill"):
            parts = line.split(maxsplit=1)
            arg = parts[1].strip() if len(parts) > 1 else ""
            if not arg or arg in {"off", "auto", "clear"}:
                agent.set_forced_skill(None)
                console.print("[yellow]已取消强制 Skill，改回按问题自动选用。[/yellow]")
            else:
                ids = {s["id"] for s in list_skills(ws)}
                if arg not in ids:
                    console.print(f"[red]没有这个 Skill：{arg}[/red]")
                    _print_skills(ws)
                else:
                    agent.set_forced_skill(arg)
                    console.print(f"[green]已强制使用 Skill：{arg}[/green]")
            continue
        if line == "/memory":
            ensure_default_user_memory(ws)
            console.print(Panel(read_long_term_memory(ws) or "(空)", title="长期记忆", border_style="cyan"))
            console.print(f"[dim]全局目录：{global_memory_dir()}[/dim]")
            console.print(f"[dim]MEMORY.md：{memory_md_path()}[/dim]")
            console.print(f"[dim]今日日记：{daily_log_path()}[/dim]")
            console.print(f"[dim]history：{history_path()}[/dim]")
            console.print(f"[dim]tokens：{tokens_path()}[/dim]")
            console.print(f"[dim]项目 MEMORY：{project_memory_path(ws)}[/dim]")
            continue
        if line == "/tokens":
            stats = summarize_tokens()
            console.print(
                Panel(
                    f"calls            : {stats['calls']}\n"
                    f"prompt_tokens    : {stats['prompt_tokens']}\n"
                    f"completion_tokens: {stats['completion_tokens']}\n"
                    f"total_tokens     : {stats['total_tokens']}\n"
                    f"by_model         : {stats.get('by_model')}\n"
                    f"file             : {stats.get('path')}",
                    title="Token 计量",
                    border_style="magenta",
                )
            )
            continue
        if line.startswith("/remember"):
            parts = line.split(maxsplit=1)
            rest = parts[1].strip() if len(parts) > 1 else ""
            if not rest:
                console.print(
                    "[yellow]用法：/remember 事实\n"
                    "      /remember project 本仓库约定…\n"
                    "      /remember daily 今天做了…\n"
                    "      /remember topic:姓名 李晨雨[/yellow]"
                )
                continue
            bucket = "user"
            topic = None
            fact = rest
            if rest.startswith("project "):
                bucket = "project"
                fact = rest[len("project ") :].strip()
            elif rest.startswith("daily "):
                bucket = "daily"
                fact = rest[len("daily ") :].strip()
            elif rest.startswith("user "):
                fact = rest[len("user ") :].strip()
            # /remember topic:姓名 李晨雨
            if fact.lower().startswith("topic:"):
                body = fact[6:].strip()
                if " " in body:
                    topic, fact = body.split(None, 1)
                else:
                    console.print("[yellow]用法：/remember topic:姓名 李晨雨[/yellow]")
                    continue
            msg = write_memory(ws, fact, bucket=bucket, topic=topic)
            agent.refresh_system_prompt()
            console.print(f"[green]{msg}[/green]")
            continue
        if line == "/team":
            if "list_teammates" not in agent.tools.names():
                console.print("[yellow]当前未启用 Agent Team[/yellow]")
            else:
                raw = agent.tools.call("list_teammates", {})
                try:
                    data = json.loads(raw)
                    console.print(data.get("team") or raw)
                except json.JSONDecodeError:
                    console.print(raw)
            continue
        if line == "/inbox":
            if "read_inbox" not in agent.tools.names():
                console.print("[yellow]当前未启用 inbox[/yellow]")
            else:
                raw = agent.tools.call("read_inbox", {})
                try:
                    data = json.loads(raw)
                    msgs = data.get("inbox") or []
                    if not msgs:
                        console.print("[dim]lead inbox 为空[/dim]")
                    else:
                        console.print_json(data=msgs)
                except json.JSONDecodeError:
                    console.print(raw)
            continue
        if line == "/clear":
            _maybe_distill(agent, "清空前")
            forced = agent.forced_skill_id
            agent = _make_agent(settings, yes=yes, forced_skill_id=forced)
            console.print("[yellow]已清空本轮对话（长期记忆仍保留；强制 Skill 如有则保持）。[/yellow]")
            continue

        try:
            agent.ask(line)
        except Exception as e:  # noqa: BLE001
            console.print(f"[red]失败:[/red] {e}")
            continue
        console.print(f"[dim]trace → {agent.trace.path}[/dim]\n")


@app.callback()
def main(
    ctx: typer.Context,
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w"),
    model: Optional[str] = typer.Option(None, "--model", "-m"),
    yes: bool = typer.Option(False, "--yes", "-y", help="危险操作不再确认"),
) -> None:
    """无子命令时直接进入对话框。"""
    if ctx.invoked_subcommand is None:
        interactive(workspace=workspace, model=model, yes=yes)


@app.command()
def version() -> None:
    console.print(f"tangyuan {__version__}")


@app.command()
def run(
    task: str = typer.Argument(..., help="一次性任务"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w"),
    model: Optional[str] = typer.Option(None, "--model", "-m"),
    max_steps: Optional[int] = typer.Option(None, "--max-steps"),
    yes: bool = typer.Option(False, "--yes", "-y"),
) -> None:
    """单次任务（非交互）。"""
    settings = load_settings(workspace=workspace, model=model, max_steps=max_steps)
    agent = _make_agent(settings, yes=yes)
    console.print(
        Panel(
            f"model: {settings.model}\nworkspace: {settings.resolve_workspace()}",
            title="汤圆 · 单次任务",
            border_style="blue",
        )
    )
    try:
        agent.ask(task)
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]失败:[/red] {e}")
        raise typer.Exit(1) from e
    console.print(f"[dim]trace → {agent.trace.path}[/dim]")


@app.command("chat")
def chat_cmd(
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w"),
    model: Optional[str] = typer.Option(None, "--model", "-m"),
    yes: bool = typer.Option(False, "--yes", "-y"),
) -> None:
    """显式进入对话框（与直接运行 tangyuan 相同）。"""
    interactive(workspace=workspace, model=model, yes=yes)


@app.command("tools")
def list_tools() -> None:
    from pathlib import Path

    tools = build_default_tools(Path(".").resolve())
    table = Table(title="汤圆内置工具")
    table.add_column("工具", style="cyan")
    table.add_column("说明")
    for schema in tools.schemas():
        fn = schema["function"]
        table.add_row(fn["name"], fn["description"])
    console.print(table)


@app.command("show-trace")
def show_trace(path: str = typer.Argument(...)) -> None:
    text = open(path, encoding="utf-8").read()
    console.print(Syntax(text, "json", word_wrap=True))


if __name__ == "__main__":
    app()
