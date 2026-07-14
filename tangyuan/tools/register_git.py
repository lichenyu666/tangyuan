"""注册 git 工具：status / diff / log / add / commit / show / branch。

只读工具直接放行；写操作（add / commit）走 ToolContext 的 confirm。
"""

from __future__ import annotations

import json
from typing import Any, Dict

from tangyuan.tools.context import ToolContext
from tangyuan.tools.git import (
    git_add,
    git_branch,
    git_commit,
    git_diff,
    git_log,
    git_show,
    git_status,
)
from tangyuan.tools.registry import ToolSpec


def register_git_tools(reg, ctx: ToolContext, *, read_only: bool = False) -> None:
    workspace = ctx.workspace

    reg.register(
        ToolSpec(
            name="git_status",
            description=(
                "查看 git 工作区状态（porcelain 格式）。"
                "改动文件、暂存区、当前分支一目了然。无参数即可调用。"
            ),
            parameters={
                "type": "object",
                "properties": {},
            },
        ),
        lambda args: git_status(workspace),
    )

    reg.register(
        ToolSpec(
            name="git_diff",
            description=(
                "查看 git 改动 diff。默认看未暂存改动；staged=true 看已暂存改动。"
                "可选 path 限定到某文件。返回 diff 文本（过长会截断）。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "staged": {"type": "boolean", "default": False},
                    "path": {"type": "string", "description": "可选：限定单个文件"},
                    "max_lines": {"type": "integer", "default": 200},
                },
            },
        ),
        lambda args: git_diff(
            workspace,
            staged=bool(args.get("staged")),
            path=args.get("path"),
            max_lines=int(args.get("max_lines") or 200),
        ),
    )

    reg.register(
        ToolSpec(
            name="git_log",
            description="查看 git 提交历史（默认 oneline 简短格式，最近 10 条）。",
            parameters={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 10},
                    "oneline": {"type": "boolean", "default": True},
                },
            },
        ),
        lambda args: git_log(
            workspace,
            limit=int(args.get("limit") or 10),
            oneline=bool(args.get("oneline", True)),
        ),
    )

    reg.register(
        ToolSpec(
            name="git_show",
            description="查看某个 commit 的详情（message + diff）。ref 可以是 commit hash、HEAD、HEAD~1 等。",
            parameters={
                "type": "object",
                "properties": {
                    "ref": {"type": "string", "description": "如 HEAD / HEAD~1 / abc1234"},
                    "max_lines": {"type": "integer", "default": 200},
                },
                "required": ["ref"],
            },
        ),
        lambda args: git_show(
            workspace,
            args["ref"],
            max_lines=int(args.get("max_lines") or 200),
        ),
    )

    reg.register(
        ToolSpec(
            name="git_branch",
            description="查看当前所在 git 分支名。无参数。",
            parameters={"type": "object", "properties": {}},
        ),
        lambda args: git_branch(workspace),
    )

    if not read_only:
        def add_handler(args: Dict[str, Any]) -> str:
            paths = args.get("paths") or []
            if not isinstance(paths, list):
                return json.dumps({"ok": False, "error": "paths 必须是数组"}, ensure_ascii=False)
            preview = " ".join(paths) if paths else "(空)"
            if ctx.confirm_writes and ctx.confirm is not None:
                if not ctx.need_confirm("git add", preview):
                    return json.dumps({"ok": False, "error": "用户取消"}, ensure_ascii=False)
            return git_add(workspace, list(paths))

        reg.register(
            ToolSpec(
                name="git_add",
                description=(
                    "把改动加入暂存区。paths 为文件路径数组；用 '.' 或 '-A' 添加全部。"
                    "需要用户确认（-y 时跳过）。"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "paths": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "如 ['src/a.py', 'README.md']，或 ['.']",
                        },
                    },
                    "required": ["paths"],
                },
            ),
            add_handler,
        )

        def commit_handler(args: Dict[str, Any]) -> str:
            message = (args.get("message") or "").strip()
            if not message:
                return json.dumps({"ok": False, "error": "message 不能为空"}, ensure_ascii=False)
            add_all = bool(args.get("add_all"))
            preview = message if len(message) <= 200 else message[:200] + "…"
            if add_all:
                preview = "(add -A 后)\n" + preview
            if ctx.confirm_writes and ctx.confirm is not None:
                if not ctx.need_confirm("git commit", preview):
                    return json.dumps({"ok": False, "error": "用户取消"}, ensure_ascii=False)
            return git_commit(workspace, message, add_all=add_all)

        reg.register(
            ToolSpec(
                name="git_commit",
                description=(
                    "提交暂存区到仓库。message 必填。add_all=true 会先 git add -A 再提交。"
                    "需要用户确认（-y 时跳过）。返回 commit 结果与 stdout。"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "message": {"type": "string", "description": "commit message"},
                        "add_all": {"type": "boolean", "default": False},
                    },
                    "required": ["message"],
                },
            ),
            commit_handler,
        )
