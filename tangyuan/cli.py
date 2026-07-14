"""汤圆 CLI — 带品牌主题的终端界面。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from tangyuan import __version__
from tangyuan.agent import TangyuanAgent
from tangyuan.config import load_settings
from tangyuan.memory import (
    daily_log_path,
    ensure_default_user_memory,
    memory_md_path,
    project_memory_path,
    read_long_term_memory,
    summarize_tokens,
    write_memory,
)
from tangyuan.skills import list_skills
from tangyuan.tools import build_default_tools
from tangyuan.trace import TraceLogger
from tangyuan.ui import (
    confirm_ui,
    console,
    details_on,
    print_banner,
    print_dim,
    print_err,
    print_final,
    print_help,
    print_ok,
    print_plan,
    print_stream_delta,
    print_stream_end,
    print_stream_start,
    print_tool_call,
    print_tool_result,
    print_warn,
    prompt_label,
    reset_stream_flag,
    set_details,
    skills_table,
    stream_had_text,
    tools_table,
)

app = typer.Typer(
    add_completion=False,
    invoke_without_command=True,
    help="汤圆 Tangyuan — 终端 Agent",
)


def _on_event(kind: str, **payload) -> None:
    if kind == "step":
        if details_on():
            print_dim(f"── {payload['step']}/{payload['max_steps']} ──")
        return
    if kind == "stream_start":
        print_stream_start()
        return
    if kind == "stream_delta":
        print_stream_delta(payload.get("delta") or "")
        return
    if kind == "stream_end":
        print_stream_end()
        return
    if kind == "assistant_delta":
        # 兼容旧调用：直接增量打印
        print_stream_start()
        print_stream_delta(payload.get("content") or "")
        print_stream_end()
        return
    if kind == "tool_call":
        print_tool_call(payload["name"], payload.get("args") or {})
        return
    if kind == "tool_result":
        print_tool_result(str(payload.get("result", "")))
        return
    if kind == "plan":
        items = payload.get("items") or []
        if items:
            print_plan(items)
        elif details_on():
            print_dim("计划已清空")
        return
    if kind == "plan_stall":
        print_warn(
            "计划未办完，继续推进" if payload.get("gate") else "计划卡住，请换路径"
        )
        return
    if kind == "subagent":
        print_dim(f"♟ {str(payload.get('preview', ''))[:80]}")
        return
    if kind == "spin":
        print_warn("疑似空转，已提醒换路径")
        return
    if kind == "final":
        # 流式期间已逐字显示；这里只在未流式时（max_steps/异常）补 Panel
        if stream_had_text():
            reset_stream_flag()
            console.print()
            return
        print_final(payload.get("content") or "", model="")
        return
    if kind == "compact" and details_on():
        print_dim(
            f"会话压缩 · 归档 {payload.get('old')} · 保留 {payload.get('kept')}"
        )
        return
    if kind == "distill" and details_on():
        items = payload.get("items") or []
        if items:
            print_dim(f"已记项目笔记 {len(items)} 条")


def _make_agent(
    settings,
    yes: bool,
    forced_skill_id: Optional[str] = None,
    on_event=None,
    read_only: bool = False,
) -> TangyuanAgent:
    ws = settings.resolve_workspace()
    if yes:
        confirm = None
        confirm_writes = False
        confirm_shell = False
    else:
        confirm = confirm_ui
        confirm_writes = settings.confirm_writes
        confirm_shell = settings.require_confirm_shell
    tools = build_default_tools(
        ws,
        settings.shell_timeout,
        confirm=confirm,
        confirm_writes=confirm_writes,
        confirm_shell=confirm_shell,
        settings=settings,
        read_only=read_only,
    )
    trace = TraceLogger(ws)
    return TangyuanAgent(
        settings,
        tools,
        trace,
        on_event=on_event or _on_event,
        forced_skill_id=forced_skill_id,
    )


def _maybe_distill(agent: TangyuanAgent, label: str) -> None:
    try:
        written = agent.distill_project_memory()
    except Exception as e:  # noqa: BLE001
        if details_on():
            print_dim(f"蒸馏跳过：{e}")
        return
    if written and details_on():
        print_dim(f"{label}：写入 {len(written)} 条")


def interactive(
    workspace: Optional[str] = None,
    model: Optional[str] = None,
    yes: bool = False,
) -> None:
    settings = load_settings(workspace=workspace, model=model)
    ws = settings.resolve_workspace()
    print_banner(settings.model, ws)

    def on_event(kind: str, **payload) -> None:
        if kind == "final":
            # 流式期间已逐字显示；非流式（max_steps/异常）才用 Panel
            if stream_had_text():
                reset_stream_flag()
                console.print()
                return
            print_final(payload.get("content") or "", model=settings.model)
            return
        _on_event(kind, **payload)

    agent = _make_agent(settings, yes=yes, on_event=on_event)

    while True:
        try:
            line = console.input(prompt_label()).strip()
        except (EOFError, KeyboardInterrupt):
            _maybe_distill(agent, "退出前")
            console.print()
            print_dim("再见")
            break

        if not line:
            continue
        if line in {"/exit", "/quit", "exit", "quit"}:
            _maybe_distill(agent, "退出前")
            print_dim("再见")
            break
        if line in {"/help", "help"}:
            print_help()
            continue
        if line in {"/details", "/verbose"}:
            set_details(not details_on())
            print_ok(f"细节 {'开' if details_on() else '关'}")
            continue
        if line == "/tools":
            list_tools()
            continue
        if line == "/skills":
            rows = list_skills(ws)
            if not rows:
                print_dim("还没有 skills")
            else:
                skills_table(rows)
            continue
        if line.startswith("/skill"):
            parts = line.split(maxsplit=1)
            arg = parts[1].strip() if len(parts) > 1 else ""
            if not arg or arg in {"off", "auto", "clear"}:
                agent.set_forced_skill(None)
                print_dim("已取消强制 Skill")
            else:
                ids = {s["id"] for s in list_skills(ws)}
                if arg not in ids:
                    print_err(f"没有 Skill：{arg}")
                    skills_table(list_skills(ws))
                else:
                    agent.set_forced_skill(arg)
                    print_ok(f"强制 Skill：{arg}")
            continue
        if line == "/memory":
            ensure_default_user_memory(ws)
            console.print(read_long_term_memory(ws) or "(空)", style="ty.text")
            if details_on():
                print_dim(f"{memory_md_path()} · {daily_log_path()}")
                print_dim(str(project_memory_path(ws)))
            continue
        if line == "/tokens":
            stats = summarize_tokens()
            print_dim(
                f"tokens {stats['total_tokens']} · calls {stats['calls']}"
            )
            continue
        if line.startswith("/remember"):
            parts = line.split(maxsplit=1)
            rest = parts[1].strip() if len(parts) > 1 else ""
            if not rest:
                print_dim("/remember 事实 | project … | daily … | topic:键 值")
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
            if fact.lower().startswith("topic:"):
                body = fact[6:].strip()
                if " " in body:
                    topic, fact = body.split(None, 1)
                else:
                    print_dim("/remember topic:姓名 李晨雨")
                    continue
            msg = write_memory(ws, fact, bucket=bucket, topic=topic)
            agent.refresh_system_prompt()
            print_ok(msg)
            continue
        if line == "/team":
            if "list_teammates" not in agent.tools.names():
                print_dim("未启用 Team")
            else:
                raw = agent.tools.call("list_teammates", {})
                try:
                    data = json.loads(raw)
                    console.print(data.get("team") or raw, style="ty.text")
                except json.JSONDecodeError:
                    console.print(raw)
            continue
        if line == "/inbox":
            if "read_inbox" not in agent.tools.names():
                print_dim("未启用 inbox")
            else:
                raw = agent.tools.call("read_inbox", {})
                try:
                    data = json.loads(raw)
                    msgs = data.get("inbox") or []
                    if not msgs:
                        print_dim("inbox 空")
                    else:
                        console.print_json(data=msgs)
                except json.JSONDecodeError:
                    console.print(raw)
            continue
        if line == "/clear":
            _maybe_distill(agent, "清空前")
            forced = agent.forced_skill_id
            agent = _make_agent(
                settings, yes=yes, forced_skill_id=forced, on_event=on_event
            )
            print_dim("已清空本轮")
            continue

        try:
            agent.ask(line)
        except Exception as e:  # noqa: BLE001
            print_err(str(e))
            continue
        if details_on():
            print_dim(str(agent.trace.path))


@app.callback()
def main(
    ctx: typer.Context,
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w"),
    model: Optional[str] = typer.Option(None, "--model", "-m"),
    yes: bool = typer.Option(False, "--yes", "-y", help="危险操作不再确认"),
) -> None:
    if ctx.invoked_subcommand is None:
        interactive(workspace=workspace, model=model, yes=yes)


@app.command()
def version() -> None:
    console.print(f"[ty.brand]tangyuan[/] [ty.muted]{__version__}[/]")


@app.command()
def run(
    task: str = typer.Argument(..., help="一次性任务"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w"),
    model: Optional[str] = typer.Option(None, "--model", "-m"),
    max_steps: Optional[int] = typer.Option(None, "--max-steps"),
    yes: bool = typer.Option(False, "--yes", "-y"),
    details: bool = typer.Option(False, "--details"),
) -> None:
    if details:
        set_details(True)
    settings = load_settings(workspace=workspace, model=model, max_steps=max_steps)

    def on_event(kind: str, **payload) -> None:
        if kind == "final":
            # 流式期间已逐字显示；非流式（max_steps/异常）才用 Panel
            if stream_had_text():
                reset_stream_flag()
                console.print()
                return
            print_final(payload.get("content") or "", model=settings.model)
            return
        _on_event(kind, **payload)

    agent = _make_agent(settings, yes=yes, on_event=on_event)
    print_dim(f"汤圆 · {settings.model} · {settings.resolve_workspace()}")
    try:
        agent.ask(task)
    except Exception as e:  # noqa: BLE001
        print_err(str(e))
        raise typer.Exit(1) from e


@app.command("chat")
def chat_cmd(
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w"),
    model: Optional[str] = typer.Option(None, "--model", "-m"),
    yes: bool = typer.Option(False, "--yes", "-y"),
) -> None:
    interactive(workspace=workspace, model=model, yes=yes)


@app.command("plan")
def plan_cmd(
    task: str = typer.Argument(..., help="要规划的任务"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w"),
    model: Optional[str] = typer.Option(None, "--model", "-m"),
    yes: bool = typer.Option(False, "--yes", "-y"),
    out: Optional[str] = typer.Option(None, "--out", "-o", help="计划文件路径，默认 <workspace>/.tangyuan/plan.md"),
) -> None:
    """Plan Mode：只用只读工具探索，产出 plan.md 供用户确认后再执行。"""
    from rich.panel import Panel
    from tangyuan.ui.theme import GOLD

    settings = load_settings(workspace=workspace, model=model)
    ws = settings.resolve_workspace()
    print_banner(settings.model, ws)
    print_dim("[ty.brand]Plan Mode[/] · 只读探索 → 产出计划 → 等待确认")
    print_dim("[ty.muted]写工具已禁用；agent 只能读、搜、看 git[/]")
    console.print()

    def on_event(kind: str, **payload) -> None:
        if kind == "final":
            if stream_had_text():
                reset_stream_flag()
                console.print()
                return
            print_final(payload.get("content") or "", model=settings.model)
            return
        _on_event(kind, **payload)

    agent = _make_agent(settings, yes=yes, on_event=on_event, read_only=True)
    # 给 agent 一个强约束的提示，让它产出结构化计划
    plan_prompt = (
        f"【任务】{task}\n\n"
        "你现在处于 Plan Mode：\n"
        "1) 用只读工具（read_file / list_dir / search_text / search_codebase / git_status 等）"
        "探索当前 workspace，理解任务涉及的文件与改动范围。\n"
        "2) 不要尝试写文件 / 跑写操作的 shell / git add / git commit。\n"
        "3) 探索完后产出结构化计划（Markdown 格式），含：\n"
        "   - 任务概述\n"
        "   - 涉及文件（带路径）\n"
        "   - 计划步骤（带文件 + what/why/how）\n"
        "   - 风险与权衡\n"
        "   - 验证步骤\n"
        "4) 输出计划即可，不要执行任何修改。\n"
    )
    try:
        plan_text = agent.ask(plan_prompt)
    except Exception as e:  # noqa: BLE001
        print_err(str(e))
        raise typer.Exit(1) from e

    # 把计划写到文件
    if out:
        plan_path = Path(out).resolve()
    else:
        plan_path = ws / ".tangyuan" / "plan.md"
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(plan_text, encoding="utf-8")

    console.print()
    console.print(
        Panel(
            f"计划已写入：[ty.path]{plan_path}[/]\n\n"
            "请 review；确认后用：\n"
            "  [ty.accent]tangyuan run \"按 plan.md 执行\" -w <workspace>[/]",
            title="[ty.brand]Plan Mode 完成[/]",
            border_style=GOLD,
            box=ROUNDED,
            padding=(1, 2),
        )
    )


@app.command("list-tools")
def list_tools() -> None:
    tools = build_default_tools(Path(".").resolve())
    rows = []
    for schema in tools.schemas():
        fn = schema["function"]
        desc = fn["description"]
        if len(desc) > 52:
            desc = desc[:52] + "…"
        rows.append((fn["name"], desc))
    tools_table(rows)


@app.command("show-trace")
def show_trace(path: str = typer.Argument(...)) -> None:
    from rich.panel import Panel
    from tangyuan.ui.theme import GOLD

    text = open(path, encoding="utf-8").read()
    console.print(Panel(text, title=path, border_style=GOLD))


@app.command("eval")
def eval_cmd(
    skip_network: bool = typer.Option(False, "--skip-network", help="跳过依赖外网的用例"),
    only: Optional[str] = typer.Option(None, "--only", help="只跑指定 id（逗号分隔）"),
    report: str = typer.Option("eval_report.md", "--report", "-r", help="报告输出路径"),
    stop_on_fail: bool = typer.Option(False, "--stop-on-fail", help="首个失败即停"),
    model: Optional[str] = typer.Option(None, "--model", "-m"),
) -> None:
    """跑评测集，输出成功率报告。"""
    from tangyuan.eval import DEFAULT_CASES, run_eval, save_report
    from tangyuan.ui.theme import GOLD, JADE, ROSE

    only_ids = None
    if only:
        only_ids = [s.strip() for s in only.split(",") if s.strip()]

    console.print()
    console.print(f"[ty.brand]评测启动[/] · {len(DEFAULT_CASES)} 个用例")
    if skip_network:
        console.print("[ty.muted]跳过 network 用例[/]")
    if only_ids:
        console.print(f"[ty.muted]仅跑: {', '.join(only_ids)}[/]")
    console.print()

    def on_progress(res, idx, total) -> None:
        mark = "[ty.ok]✓[/]" if res.passed else "[ty.err]✗[/]"
        console.print(
            f"  {mark} [{idx}/{total}] [ty.tool]{res.case_id}[/] "
            f"[ty.muted]{res.title}[/]  [ty.muted]{res.duration_sec:.1f}s[/]"
        )

    result = run_eval(
        DEFAULT_CASES,
        model=model,
        skip_network=skip_network,
        only=only_ids,
        stop_on_fail=stop_on_fail,
        on_progress=on_progress,
    )

    success_rate = (result.passed / result.total * 100) if result.total else 0
    console.print()
    console.print(
        f"[ty.brand]评测完成[/] · 通过 [ty.ok]{result.passed}[/] / {result.total} "
        f"· 失败 [ty.err]{result.failed}[/] · 跳过 [ty.muted]{result.skipped}[/] "
        f"· 耗时 {result.duration_sec:.1f}s"
    )
    console.print(
        f"[ty.brand]成功率[/] · [bold]{success_rate:.1f}%[/]"
    )

    report_path = Path(report).resolve()
    save_report(result, report_path, model=model or "")
    console.print(f"[ty.muted]报告：{report_path}[/]")

    if result.failed > 0:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
