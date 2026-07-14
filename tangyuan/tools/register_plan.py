"""任务规划工具：update_plan。"""

from __future__ import annotations

import json
from typing import Any

from tangyuan.agent.plan import TaskPlan
from tangyuan.tools.registry import ToolRegistry, ToolSpec


def register_plan_tools(reg: ToolRegistry, plan: TaskPlan) -> None:
    def _update_plan(args: dict[str, Any]) -> str:
        items = args.get("items")
        if not isinstance(items, list):
            return json.dumps(
                {"ok": False, "error": "items 必须是数组"},
                ensure_ascii=False,
            )
        merge = bool(args.get("merge", False))
        if merge:
            result = plan.merge(items)
        else:
            result = plan.replace(items)
        return json.dumps(result, ensure_ascii=False)

    reg.register(
        ToolSpec(
            name="update_plan",
            description=(
                "维护结构化任务计划（复杂/多步任务必须先用本工具拆解再动手）。"
                "默认整表替换；merge=true 时按 id 合并更新。"
                "状态：pending / in_progress / completed / cancelled；"
                "同时只能有一个 in_progress。"
                "完成一步立刻勾 completed 再开下一步；卡住或改方向先改计划。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "description": "计划步骤列表",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {
                                    "type": "string",
                                    "description": "稳定步骤 id，如 1、explore、fix-tests",
                                },
                                "content": {
                                    "type": "string",
                                    "description": "可检查的一步，动词开头，具体可验证",
                                },
                                "status": {
                                    "type": "string",
                                    "enum": [
                                        "pending",
                                        "in_progress",
                                        "completed",
                                        "cancelled",
                                    ],
                                    "description": "步骤状态",
                                },
                            },
                            "required": ["id", "content", "status"],
                        },
                    },
                    "merge": {
                        "type": "boolean",
                        "default": False,
                        "description": "true=按 id 合并；false=整表替换（默认）",
                    },
                },
                "required": ["items"],
            },
        ),
        _update_plan,
    )


def ensure_plan_tool(reg: ToolRegistry, plan: TaskPlan | None) -> None:
    """用会话内 TaskPlan 绑定（或覆盖）update_plan。"""
    if plan is None:
        return
    register_plan_tools(reg, plan)
