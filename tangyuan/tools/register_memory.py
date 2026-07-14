from __future__ import annotations

import json
from typing import Any, Dict

from tangyuan.memory import recall_memory, write_memory
from tangyuan.skills import list_skills, load_skill_body
from tangyuan.tools.context import ToolContext
from tangyuan.tools.registry import ToolSpec


def register_memory_tools(reg, ctx: ToolContext) -> None:
    workspace = ctx.workspace

    reg.register(
        ToolSpec(
            name="remember",
            description=(
                "写入长期记忆。"
                "user=全局用户画像（跨目录）；project=当前仓库笔记；daily=今日日记。"
                "稳定事实务必带 topic（同名会覆盖）；用户说「记住：…」时使用。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "fact": {"type": "string", "description": "要记住的一句话事实"},
                    "bucket": {
                        "type": "string",
                        "enum": ["user", "project", "daily"],
                        "default": "user",
                        "description": "user=MEMORY.md，project=项目MEMORY，daily=今日日记",
                    },
                    "topic": {
                        "type": "string",
                        "description": "可选主题键，如 姓名/学校/偏好；有则覆盖更新，无则追加",
                    },
                },
                "required": ["fact"],
            },
        ),
        lambda args: json.dumps(
            {
                "ok": True,
                "result": write_memory(
                    workspace,
                    args["fact"],
                    bucket=args.get("bucket") or "user",
                    topic=args.get("topic"),
                ),
            },
            ensure_ascii=False,
        ),
    )

    reg.register(
        ToolSpec(
            name="recall_memory",
            description=(
                "按需召回长期记忆（渐进披露）。"
                "系统提示通常只有短画像；查项目约定、完整笔记或按关键词过滤时用本工具。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "bucket": {
                        "type": "string",
                        "enum": ["user", "project", "daily", "all"],
                        "default": "all",
                    },
                    "query": {
                        "type": "string",
                        "description": "可选关键词，只返回包含该词的行",
                    },
                },
            },
        ),
        lambda args: json.dumps(
            {
                "ok": True,
                "memory": recall_memory(
                    workspace,
                    bucket=args.get("bucket") or "all",
                    query=args.get("query"),
                ),
            },
            ensure_ascii=False,
        ),
    )


def register_skill_tools(reg, ctx: ToolContext) -> None:
    workspace = ctx.workspace

    def _load_skill(args: Dict[str, Any]) -> str:
        skill_id = (args.get("skill_id") or "").strip()
        if not skill_id:
            return json.dumps({"ok": False, "error": "缺少 skill_id"}, ensure_ascii=False)
        body = load_skill_body(workspace, skill_id)
        if not body:
            ids = [s["id"] for s in list_skills(workspace)]
            return json.dumps(
                {
                    "ok": False,
                    "error": f"未找到 Skill `{skill_id}`",
                    "available": ids,
                },
                ensure_ascii=False,
            )
        return json.dumps(
            {"ok": True, "skill_id": skill_id, "body": body},
            ensure_ascii=False,
        )

    reg.register(
        ToolSpec(
            name="load_skill",
            description=(
                "按需加载某个 Skill 的完整剧本（渐进式披露）。"
                "系统提示里通常只有摘要；意图匹配后必须先调用本工具，再按返回的步骤执行。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "skill_id": {
                        "type": "string",
                        "description": "Skill id，如 fix-error / explain-repo / make-pptx",
                    },
                },
                "required": ["skill_id"],
            },
        ),
        _load_skill,
    )
