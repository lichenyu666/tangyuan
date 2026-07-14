"""汤圆界面组件：启动页、流式输出、工具轨、回答卡、状态条。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import typer
from rich.align import Align
from rich.box import ROUNDED, SIMPLE
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from tangyuan import __version__
from tangyuan.ui.theme import APRICOT, GOLD, GOLD_DIM, INK_SOFT, JADE, MARK, MIST, RICE, STEEL, console

_SHOW_DETAILS = False

# 流式状态：当前流式是否激活 / 是否已产出过文本
_STREAM_ACTIVE = False
_STREAM_HAD_TEXT = False


def set_details(on: bool) -> None:
    global _SHOW_DETAILS
    _SHOW_DETAILS = on


def details_on() -> bool:
    return _SHOW_DETAILS


def short_path(ws: Path) -> str:
    home = Path.home()
    try:
        return f"~/{ws.relative_to(home)}"
    except ValueError:
        return str(ws)


def print_banner(model: str, ws: Path) -> None:
    console.print()
    # 极简 header（参考 Claude Code）：一行搞定，不堆叠元素
    header = Text()
    header.append(MARK, style="ty.brand")
    header.append("  ·  ", style="ty.muted")
    header.append(model, style="ty.text")
    header.append("  ·  ", style="ty.muted")
    header.append(short_path(ws), style="ty.path")
    header.append("  ·  ", style="ty.muted")
    header.append("/help", style="ty.accent")
    console.print(header)
    console.print(Rule(style="ty.rule", characters="─"))
    console.print(Text("  说需求 / 命令以 / 开头", style="ty.muted"))
    console.print()


def print_help() -> None:
    body = """\
直接说需求。`@路径` 附带文件。

| 命令 | |
|------|--|
| `/help` | 帮助 |
| `/details` | 工具细节开关 |
| `/tools` `/skills` | 工具与技能 |
| `/team` `/inbox` | 队友 |
| `/memory` `/remember` `/tokens` | 记忆 |
| `/clear` `/exit` | 清空 / 退出 |

复杂任务会自动拆计划；可派子代理；MCP 含 time / GitHub。
"""
    console.print(
        Panel(
            Markdown(body),
            title="[ty.brand]帮助[/]",
            border_style=STEEL,
            box=ROUNDED,
            padding=(1, 2),
        )
    )


# ── 流式输出 ────────────────────────────────────────────────────────

# 流式开始时是否已打印了"开始分隔线"
_STREAM_HEAD_PRINTED = False


def print_stream_start() -> None:
    """开始一段流式输出。"""
    global _STREAM_ACTIVE, _STREAM_HAD_TEXT, _STREAM_HEAD_PRINTED
    _STREAM_ACTIVE = True
    _STREAM_HAD_TEXT = False
    _STREAM_HEAD_PRINTED = False


def print_stream_delta(text: str) -> None:
    """增量打印一段文本（不换行）。"""
    global _STREAM_HAD_TEXT, _STREAM_HEAD_PRINTED
    if not _STREAM_ACTIVE:
        print_stream_start()
    if text:
        # 在第一段文本前打印一个精致的 mint 色 ✦ 锚点，不喧宾夺主
        if not _STREAM_HEAD_PRINTED:
            console.print()
            console.print(Text("  ✦ ", style="ty.accent.green"), end="", highlight=False)
            _STREAM_HEAD_PRINTED = True
        _STREAM_HAD_TEXT = True
        console.print(text, style="ty.text", end="", highlight=False, soft_wrap=True)


def print_stream_end() -> None:
    """流式结束：换行收尾（不再打印结束 Rule，避免分隔线太密集）。"""
    global _STREAM_ACTIVE, _STREAM_HEAD_PRINTED
    if _STREAM_ACTIVE:
        if _STREAM_HAD_TEXT:
            console.print()
        _STREAM_HEAD_PRINTED = False
        _STREAM_ACTIVE = False


def stream_had_text() -> bool:
    """最近一次流式是否产出过文本（供 final 渲染决策）。"""
    return _STREAM_HAD_TEXT


def reset_stream_flag() -> None:
    """清空流式标志，便于下一轮重新判断。"""
    global _STREAM_HAD_TEXT
    _STREAM_HAD_TEXT = False


# ── 工具调用卡片 ────────────────────────────────────────────────────

def tool_summary(name: str, args: Dict[str, Any]) -> str:
    if name == "read_file":
        return str(args.get("path") or args.get("file") or "")
    if name in {"write_file", "apply_patch"}:
        return str(args.get("path") or "")
    if name == "list_dir":
        return str(args.get("path") or ".")
    if name == "search_text":
        return str(args.get("query") or args.get("pattern") or "")
    if name == "search_codebase":
        return str(args.get("query") or "")
    if name == "run_shell":
        cmd = str(args.get("command") or "")
        return cmd if len(cmd) <= 72 else cmd[:72] + "…"
    if name == "web_search":
        return str(args.get("query") or "")
    if name == "fetch_url":
        return str(args.get("url") or "")
    if name == "load_skill":
        return str(args.get("skill_id") or "")
    if name == "update_plan":
        items = args.get("items") or []
        return f"{len(items)} 步" if isinstance(items, list) else ""
    if name == "dispatch_subagent":
        return f"{args.get('agent_type') or 'explore'}"
    if name == "spawn_teammate":
        return str(args.get("name") or "")
    if name.startswith("git_"):
        return str(args.get("path") or args.get("message") or "")[:60]
    if name.startswith("mcp_"):
        return str(args.get("query") or args.get("q") or "")[:50]
    for v in args.values():
        if isinstance(v, str) and 0 < len(v) < 72:
            return v
    return ""


# 工具图标（轻量、不依赖 emoji 字体；终端通用符号）
_TOOL_ICONS = {
    "read_file": "▸",
    "write_file": "✎",
    "apply_patch": "✎",
    "list_dir": "▸",
    "search_text": "⌕",
    "search_codebase": "⌕",
    "run_shell": "⚙",
    "web_search": "⌕",
    "fetch_url": "↘",
    "load_skill": "✦",
    "update_plan": "☷",
    "dispatch_subagent": "♟",
    "spawn_teammate": "♟",
    "open_path": "↘",
    "open_app": "↘",
    "create_pptx": "▤",
    "move_to_trash": "⌫",
    "remember": "✦",
    "recall_memory": "✦",
}


def _tool_icon(name: str) -> str:
    if name in _TOOL_ICONS:
        return _TOOL_ICONS[name]
    if name.startswith("git_"):
        return "⎇"
    if name.startswith("mcp_"):
        return "◈"
    return "┊"


def print_tool_call(name: str, args: Dict[str, Any]) -> None:
    summary = tool_summary(name, args)
    icon = _tool_icon(name)
    row = Text()
    row.append(f"  {icon} ", style="ty.accent")
    row.append(name, style="ty.tool")
    if summary:
        row.append("  ")
        row.append(summary, style="ty.muted")
    console.print(row)
    if _SHOW_DETAILS:
        raw = json.dumps(args, ensure_ascii=False)
        if len(raw) > 140:
            raw = raw[:140] + "…"
        console.print(Text(f"    {raw}", style="ty.muted"))


def print_tool_result(result: str) -> None:
    head = result[:120].lower()
    bad = '"ok": false' in head or ("error" in head and '"ok": true' not in head)
    if bad:
        preview = result.replace("\n", " ")
        if len(preview) > 100:
            preview = preview[:100] + "…"
        t = Text()
        t.append("  ✗ ", style="ty.err")
        t.append(preview, style="ty.err")
        console.print(t)
    elif _SHOW_DETAILS:
        preview = result.replace("\n", " ")
        if len(preview) > 100:
            preview = preview[:100] + "…"
        console.print(Text(f"  ✓ {preview}", style="ty.muted"))


def print_plan(items: List[Dict[str, Any]]) -> None:
    if not items:
        return
    done = sum(1 for i in items if i.get("status") == "completed")
    total = len(items)
    dots = Text("  ")
    for i in items:
        st = i.get("status")
        if st == "completed":
            dots.append("●", style="ty.ok")
        elif st == "in_progress":
            dots.append("●", style="ty.accent")
        elif st == "cancelled":
            dots.append("·", style="ty.muted")
        else:
            dots.append("○", style="ty.muted")
        dots.append(" ")
    active = next((i for i in items if i.get("status") == "in_progress"), None)
    label = (active or {}).get("content", "")[:36]
    dots.append(f"  {done}/{total}", style="ty.muted")
    if label:
        dots.append(f"  {label}", style="ty.text")
    console.print(dots)
    if _SHOW_DETAILS:
        for it in items:
            mark = {
                "pending": "○",
                "in_progress": "●",
                "completed": "✓",
                "cancelled": "–",
            }.get(it.get("status"), "○")
            console.print(
                f"    [ty.muted]{mark}[/] [ty.text]{it.get('content')}[/]"
            )


def print_final(content: str, *, model: str = "") -> None:
    """非流式 final（错误信息、max_steps 等）用精致 Panel 包裹。"""
    text = (content or "").strip() or "(空)"
    try:
        body: Any = Markdown(text)
    except Exception:  # noqa: BLE001
        body = text
    console.print()
    console.print(
        Panel(
            body,
            title="[ty.brand]汤圆[/]",
            title_align="left",
            border_style=GOLD_DIM,
            box=ROUNDED,
            padding=(0, 2),
            subtitle=f"[ty.muted]{model}[/]" if model else None,
            subtitle_align="right",
        )
    )
    console.print()


def print_warn(msg: str) -> None:
    console.print(Text(f"  ! {msg}", style="ty.warn"))


def print_err(msg: str) -> None:
    console.print(Text(f"  ✗ {msg}", style="ty.err"))


def print_dim(msg: str) -> None:
    console.print(Text(msg, style="ty.muted"))


def print_ok(msg: str) -> None:
    console.print(Text(f"  ✓ {msg}", style="ty.ok"))


def prompt_label() -> str:
    return "[ty.prompt]❯[/] "


def confirm_ui(title: str, detail: str) -> bool:
    console.print(
        Panel(
            detail if len(detail) < 500 else detail[:500] + "…",
            title=f"[ty.warn]{title}[/]",
            border_style=APRICOT,
            box=ROUNDED,
            padding=(0, 1),
        )
    )
    return typer.confirm("确认执行？", default=False)


def skills_table(rows: List[Dict[str, str]]) -> None:
    table = Table(
        box=SIMPLE,
        show_header=True,
        header_style="ty.brand",
        border_style=INK_SOFT,
        padding=(0, 1),
    )
    table.add_column("id", style="ty.accent")
    table.add_column("标题", style="ty.text")
    table.add_column("何时", style="ty.muted")
    for r in rows:
        table.add_row(r["id"], r["title"], (r.get("when") or "")[:48])
    console.print(table)


def tools_table(rows: List[tuple]) -> None:
    table = Table(
        box=SIMPLE,
        show_header=True,
        header_style="ty.brand",
        border_style=INK_SOFT,
        padding=(0, 1),
    )
    table.add_column("工具", style="ty.accent")
    table.add_column("说明", style="ty.muted")
    for name, desc in rows:
        table.add_row(name, desc)
    console.print(table)
