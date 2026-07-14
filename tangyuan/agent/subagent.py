"""子代理：独立上下文执行，只回禀摘要（对齐教学 step09 精简版）。"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from openai import OpenAI

from tangyuan.config import Settings
from tangyuan.memory import record_usage_from_response
from tangyuan.tools.registry import ToolRegistry

# 子代理拿不到：规划 / 派遣 / 记忆写入（避免污染主会话）
_BLOCKED = frozenset(
    {
        "dispatch_subagent",
        "update_plan",
        "remember",
        "move_to_trash",
        "spawn_teammate",
        "list_teammates",
        "send_message",
        "read_inbox",
        "broadcast",
    }
)

SUBAGENT_SPECS: Dict[str, Dict[str, Any]] = {
    "explore": {
        "title": "探索助手",
        "duty": "只读探索代码与目录，汇总结构与关键文件，不改文件。",
        "tools": [
            "list_dir",
            "read_file",
            "search_text",
            "load_skill",
            "recall_memory",
        ],
        "max_turns": 10,
    },
    "research": {
        "title": "调研助手",
        "duty": "查网页、抓 URL、整理资料结论；不改本地文件。",
        "tools": [
            "web_search",
            "fetch_url",
            "read_file",
            "list_dir",
            "search_text",
            "load_skill",
            "open_path",
        ],
        "max_turns": 12,
    },
    "coder": {
        "title": "编码助手",
        "duty": "读写改代码、跑命令、必要时打补丁；最后只回报做了什么。",
        "tools": [
            "list_dir",
            "read_file",
            "write_file",
            "apply_patch",
            "search_text",
            "run_shell",
            "load_skill",
            "web_search",
            "fetch_url",
        ],
        "max_turns": 16,
    },
}


def _system_prompt(spec: Dict[str, Any], purpose: str) -> str:
    purpose_line = f"\n本次目的：{purpose}" if purpose else ""
    return (
        f"你是汤圆的子代理「{spec['title']}」。\n"
        f"职责：{spec['duty']}\n"
        "规则：\n"
        "1. 只做被交代的事；用工具取证，不要编造。\n"
        "2. 结束后用简洁中文回禀：结论、关键路径/命令、未解决点。\n"
        "3. 不要调用你没有的工具；不要试图再派遣子代理。\n"
        f"{purpose_line}"
    )


def run_subagent(
    *,
    settings: Settings,
    parent_tools: ToolRegistry,
    task: str,
    agent_type: str = "explore",
    purpose: str = "",
    max_turns: Optional[int] = None,
) -> str:
    spec = SUBAGENT_SPECS.get(agent_type) or SUBAGENT_SPECS["explore"]
    allowed = [t for t in spec["tools"] if t in parent_tools.names() and t not in _BLOCKED]
    turns = max_turns or int(spec["max_turns"])

    client = OpenAI(api_key=settings.api_key, base_url=settings.base_url)
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": _system_prompt(spec, purpose)},
        {"role": "user", "content": task},
    ]
    schemas = parent_tools.schemas(allowed)

    final = ""
    for _ in range(turns):
        kwargs: Dict[str, Any] = {
            "model": settings.model,
            "messages": messages,
            "temperature": settings.temperature,
        }
        if schemas:
            kwargs["tools"] = schemas
            kwargs["tool_choice"] = "auto"
        resp = client.chat.completions.create(**kwargs)
        record_usage_from_response(
            resp,
            model=settings.model,
            workspace=str(settings.resolve_workspace()),
        )
        msg = resp.choices[0].message
        tool_calls = msg.tool_calls or []
        assistant: Dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
        if tool_calls:
            assistant["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments or "{}",
                    },
                }
                for tc in tool_calls
            ]
        messages.append(assistant)

        if not tool_calls:
            final = (msg.content or "").strip()
            break

        for tc in tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                result = json.dumps(
                    {"ok": False, "error": "工具参数不是合法 JSON"},
                    ensure_ascii=False,
                )
            else:
                if name not in allowed:
                    result = json.dumps(
                        {"ok": False, "error": f"子代理无权使用工具: {name}"},
                        ensure_ascii=False,
                    )
                else:
                    result = parent_tools.call(name, args)
            messages.append(
                {"role": "tool", "tool_call_id": tc.id, "content": result}
            )
    else:
        final = final or f"（子代理已达 max_turns={turns}，以下为最后可见内容）\n" + (
            messages[-1].get("content") or ""
        )

    return final or "(子代理无文本回禀)"


def list_subagent_types() -> str:
    lines = ["可用子代理类型："]
    for key, spec in SUBAGENT_SPECS.items():
        tools = ", ".join(spec["tools"])
        lines.append(
            f"- `{key}` {spec['title']}：{spec['duty']} 工具=[{tools}] max_turns={spec['max_turns']}"
        )
    return "\n".join(lines)
