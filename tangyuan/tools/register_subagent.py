"""dispatch_subagent 工具。"""

from __future__ import annotations

import json
from typing import Any, Dict

from tangyuan.agent.subagent import SUBAGENT_SPECS, list_subagent_types, run_subagent
from tangyuan.config import Settings
from tangyuan.tools.registry import ToolRegistry, ToolSpec


def register_subagent_tools(
    reg: ToolRegistry,
    *,
    settings: Settings,
    parent_tools: ToolRegistry,
) -> None:
    def _dispatch(args: Dict[str, Any]) -> str:
        task = (args.get("task") or "").strip()
        if not task:
            return json.dumps({"ok": False, "error": "缺少 task"}, ensure_ascii=False)
        agent_type = (args.get("agent_type") or "explore").strip()
        if agent_type not in SUBAGENT_SPECS:
            return json.dumps(
                {
                    "ok": False,
                    "error": f"未知 agent_type: {agent_type}",
                    "hint": list_subagent_types(),
                },
                ensure_ascii=False,
            )
        purpose = (args.get("purpose") or "").strip()
        max_turns = args.get("max_turns")
        try:
            summary = run_subagent(
                settings=settings,
                parent_tools=parent_tools,
                task=task,
                agent_type=agent_type,
                purpose=purpose,
                max_turns=int(max_turns) if max_turns else None,
            )
        except Exception as e:  # noqa: BLE001
            return json.dumps(
                {"ok": False, "error": f"子代理失败: {e}"},
                ensure_ascii=False,
            )
        return json.dumps(
            {
                "ok": True,
                "agent_type": agent_type,
                "summary": summary,
            },
            ensure_ascii=False,
        )

    reg.register(
        ToolSpec(
            name="dispatch_subagent",
            description=(
                "派遣子代理在独立上下文中执行细节任务，只回禀摘要（不污染主对话）。"
                "适合：大范围读代码、网页调研、隔离试错。"
                f"agent_type: {', '.join(SUBAGENT_SPECS.keys())}。"
                "不要把整件差事丢给子代理；主 Agent 仍负责 update_plan。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "交给子代理的具体任务说明",
                    },
                    "agent_type": {
                        "type": "string",
                        "enum": list(SUBAGENT_SPECS.keys()),
                        "description": "explore=只读探路；research=网页调研；coder=改代码跑命令",
                    },
                    "purpose": {
                        "type": "string",
                        "description": "可选：为什么派它（帮助聚焦回禀）",
                    },
                    "max_turns": {
                        "type": "integer",
                        "description": "可选：覆盖默认最大轮数",
                    },
                },
                "required": ["task"],
            },
        ),
        _dispatch,
    )
