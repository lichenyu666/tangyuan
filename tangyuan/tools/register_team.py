"""Agent Team 工具注册。"""

from __future__ import annotations

import json
from typing import Any

from tangyuan.agent.team import TeammateManager
from tangyuan.tools.registry import ToolRegistry, ToolSpec


def register_team_tools(reg: ToolRegistry, team: TeammateManager) -> None:
    def _spawn(args: dict[str, Any]) -> str:
        return json.dumps(
            {
                "ok": True,
                "result": team.spawn(
                    args.get("name", ""),
                    args.get("role", "teammate"),
                    args.get("prompt", ""),
                ),
                "team": team.list_all(),
            },
            ensure_ascii=False,
        )

    def _list(_args: dict[str, Any]) -> str:
        return json.dumps(
            {"ok": True, "team": team.list_all()},
            ensure_ascii=False,
        )

    def _send(args: dict[str, Any]) -> str:
        to = (args.get("to") or "").strip()
        content = (args.get("content") or "").strip()
        if not to or not content:
            return json.dumps(
                {"ok": False, "error": "需要 to 与 content"},
                ensure_ascii=False,
            )
        msg = team.bus.send(
            "lead",
            to,
            content,
            args.get("msg_type") or "message",
        )
        return json.dumps({"ok": True, "result": msg}, ensure_ascii=False)

    def _inbox(_args: dict[str, Any]) -> str:
        msgs = team.bus.read_inbox("lead")
        return json.dumps(
            {"ok": True, "inbox": msgs, "count": len(msgs)},
            ensure_ascii=False,
        )

    def _broadcast(args: dict[str, Any]) -> str:
        content = (args.get("content") or "").strip()
        if not content:
            return json.dumps(
                {"ok": False, "error": "缺少 content"},
                ensure_ascii=False,
            )
        msg = team.bus.broadcast("lead", content, team.member_names())
        return json.dumps({"ok": True, "result": msg}, ensure_ascii=False)

    reg.register(
        ToolSpec(
            name="spawn_teammate",
            description=(
                "召入/唤回固定队友（Agent Team）。队友有名字、角色、独立线程和 inbox，"
                "适合长期协作；一次性差事优先用 dispatch_subagent。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "队友名字，如 alice"},
                    "role": {
                        "type": "string",
                        "description": "职司，如 researcher / coder / reviewer",
                    },
                    "prompt": {
                        "type": "string",
                        "description": "初次任务说明；若队友已在跑则送入 inbox",
                    },
                },
                "required": ["name", "prompt"],
            },
        ),
        _spawn,
    )
    reg.register(
        ToolSpec(
            name="list_teammates",
            description="查看 Agent Team 队友名字、角色与状态。",
            parameters={"type": "object", "properties": {}},
        ),
        _list,
    )
    reg.register(
        ToolSpec(
            name="send_message",
            description="给某位固定队友发送 inbox 消息（lead → teammate）。",
            parameters={
                "type": "object",
                "properties": {
                    "to": {"type": "string"},
                    "content": {"type": "string"},
                    "msg_type": {
                        "type": "string",
                        "enum": [
                            "message",
                            "broadcast",
                            "shutdown_request",
                            "shutdown_response",
                        ],
                    },
                },
                "required": ["to", "content"],
            },
        ),
        _send,
    )
    reg.register(
        ToolSpec(
            name="read_inbox",
            description="读取并清空 lead 自己的 inbox（查看队友回禀）。",
            parameters={"type": "object", "properties": {}},
        ),
        _inbox,
    )
    reg.register(
        ToolSpec(
            name="broadcast",
            description="向所有队友广播一条消息。",
            parameters={
                "type": "object",
                "properties": {"content": {"type": "string"}},
                "required": ["content"],
            },
        ),
        _broadcast,
    )


def ensure_team(
    settings,
    tools: ToolRegistry,
    existing: TeammateManager | None = None,
) -> TeammateManager:
    from tangyuan.agent.team import team_dir_for

    if existing is not None:
        return existing
    ws = settings.resolve_workspace()
    team = TeammateManager(team_dir_for(ws), settings=settings, tools=tools)
    register_team_tools(tools, team)
    return team
