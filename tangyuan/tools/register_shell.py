from __future__ import annotations

import json
from typing import Any, Dict

from tangyuan.tools.context import ToolContext
from tangyuan.tools.registry import ToolSpec
from tangyuan.tools.shell import move_to_trash, open_app, open_path, run_shell, shell_blocked_reason


def register_shell_tools(reg, ctx: ToolContext) -> None:
    workspace = ctx.workspace

    def shell_handler(args: Dict[str, Any]) -> str:
        cmd = args.get("command") or ""
        blocked = shell_blocked_reason(cmd)
        if blocked:
            return json.dumps({"ok": False, "error": blocked}, ensure_ascii=False)
        if ctx.confirm_shell and not ctx.need_confirm("执行 Shell", cmd):
            return json.dumps({"ok": False, "error": "用户取消"}, ensure_ascii=False)
        return run_shell(workspace, cmd, ctx.shell_timeout)

    reg.register(
        ToolSpec(
            name="run_shell",
            description="在 workspace 下执行 shell。危险命令会直接拒绝；其余高危操作需确认。",
            parameters={
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        ),
        shell_handler,
    )

    reg.register(
        ToolSpec(
            name="open_path",
            description="用系统默认程序打开文件/文件夹/URL（macOS: open）。",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string", "description": "本地路径或 https URL"}},
                "required": ["path"],
            },
        ),
        lambda args: open_path(args["path"]),
    )

    reg.register(
        ToolSpec(
            name="open_app",
            description="打开 macOS 应用程序，例如 Safari、Notes、Calculator、Google Chrome。",
            parameters={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        ),
        lambda args: open_app(args["name"]),
    )

    def trash_handler(args: Dict[str, Any]) -> str:
        path = args.get("path") or ""
        if not ctx.need_confirm("移到废纸篓（可恢复）", path):
            return json.dumps({"ok": False, "error": "用户取消"}, ensure_ascii=False)
        return move_to_trash(path)

    reg.register(
        ToolSpec(
            name="move_to_trash",
            description="把文件/App 移到废纸篓（不是永久删除）。必须用户确认。",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        ),
        trash_handler,
    )
