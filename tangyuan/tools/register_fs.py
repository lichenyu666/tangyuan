from __future__ import annotations

import json
from typing import Any, Dict

from tangyuan.tools.context import ToolContext
from tangyuan.tools.fs import apply_patch, list_dir, read_file, search_text, write_file
from tangyuan.tools.registry import ToolSpec


def register_fs_tools(reg, ctx: ToolContext, *, read_only: bool = False) -> None:
    workspace = ctx.workspace

    reg.register(
        ToolSpec(
            name="list_dir",
            description="列出目录内容（相对 workspace，或绝对路径）。",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string", "default": "."}},
            },
        ),
        lambda args: list_dir(workspace, args.get("path") or "."),
    )

    reg.register(
        ToolSpec(
            name="read_file",
            description="读取文本文件。可用相对路径或用户提供的绝对路径。大文件用 offset/limit。",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "offset": {"type": "integer", "default": 1},
                    "limit": {"type": "integer", "default": 400},
                },
                "required": ["path"],
            },
        ),
        lambda args: read_file(
            workspace,
            args["path"],
            int(args.get("offset") or 1),
            int(args.get("limit") or 400),
        ),
    )

    if not read_only:
        def write_handler(args: Dict[str, Any]) -> str:
            path = args["path"]
            content = args["content"]
            if ctx.confirm_writes and ctx.confirm is not None:
                preview = content if len(content) <= 400 else content[:400] + "\n…(truncated)"
                if not ctx.need_confirm("写入文件", f"{path}\n\n{preview}"):
                    return json.dumps({"ok": False, "error": "用户取消"}, ensure_ascii=False)
            return write_file(workspace, path, content)

        reg.register(
            ToolSpec(
                name="write_file",
                description=(
                    "写入/覆盖整个文本文件（workspace 内）。"
                    "局部修改请优先用 apply_patch，避免整文件覆盖。"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["path", "content"],
                },
            ),
            write_handler,
        )

        def patch_handler(args: Dict[str, Any]) -> str:
            path = args["path"]
            old = args.get("old_string") or ""
            new = args.get("new_string")
            if new is None:
                return json.dumps({"ok": False, "error": "缺少 new_string"}, ensure_ascii=False)
            if ctx.confirm_writes and ctx.confirm is not None:
                detail = f"{path}\n--- old ---\n{old[:300]}\n--- new ---\n{str(new)[:300]}"
                if not ctx.need_confirm("应用补丁 apply_patch", detail):
                    return json.dumps({"ok": False, "error": "用户取消"}, ensure_ascii=False)
            return apply_patch(
                workspace,
                path,
                old,
                str(new),
                replace_all=bool(args.get("replace_all")),
            )

        reg.register(
            ToolSpec(
                name="apply_patch",
                description=(
                    "精确替换文件中的一段文本（改代码首选）。"
                    "old_string 必须能唯一匹配；找不到或匹配多处会失败。"
                    "replace_all=true 时替换全部相同片段。"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "old_string": {"type": "string"},
                        "new_string": {"type": "string"},
                        "replace_all": {"type": "boolean", "default": False},
                    },
                    "required": ["path", "old_string", "new_string"],
                },
            ),
            patch_handler,
        )

    reg.register(
        ToolSpec(
            name="search_text",
            description=(
                "在目录内搜索文件内容。支持正则；有 ripgrep(rg) 时优先用 rg。"
                "可用 glob 限制，如 '*.py'。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "子串或正则"},
                    "path": {"type": "string", "default": "."},
                    "glob": {"type": "string", "description": "如 *.py"},
                    "context": {
                        "type": "integer",
                        "default": 0,
                        "description": "命中行上下各几行",
                    },
                    "max_hits": {"type": "integer", "default": 50},
                    "regex": {"type": "boolean", "default": True},
                },
                "required": ["query"],
            },
        ),
        lambda args: search_text(
            workspace,
            args["query"],
            args.get("path") or ".",
            int(args.get("max_hits") or 50),
            glob=args.get("glob"),
            context=int(args.get("context") or 0),
            use_regex=bool(args.get("regex", True)),
        ),
    )
