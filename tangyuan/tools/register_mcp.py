"""注册 MCP 外部工具。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tangyuan.mcp import (
    MCP_AVAILABLE,
    ensure_default_mcp_config,
    load_mcp_tool_map,
    resolve_mcp_config,
)
from tangyuan.tools.registry import ToolRegistry, ToolSpec


def register_mcp_tools(reg: ToolRegistry, workspace: Path) -> dict[str, Any]:
    """挂载 MCP 工具。无配置时自动写入 time；有二进制则挂 github。"""
    info: dict[str, Any] = {
        "available": MCP_AVAILABLE,
        "config": str(resolve_mcp_config(workspace)),
        "servers": [],
        "tools": [],
        "warnings": [],
    }

    clients: dict[str, Any] = {}
    warnings: list[str] = []
    if MCP_AVAILABLE:
        cfg_path = ensure_default_mcp_config(workspace)
        info["config"] = str(cfg_path)
        tool_map, clients, warnings = load_mcp_tool_map(workspace)
        info["servers"] = list(clients.keys())
        info["warnings"] = warnings

        for tool_name, (client, tool) in tool_map.items():
            desc = getattr(tool, "description", None) or f"MCP {client.name}/{tool.name}"
            schema = getattr(tool, "inputSchema", None) or {
                "type": "object",
                "properties": {},
            }

            def _make_handler(c=client, t=tool):
                def _handler(args: dict[str, Any]) -> str:
                    try:
                        text = c.call_tool(t.name, args)
                        return json.dumps(
                            {
                                "ok": True,
                                "server": c.name,
                                "tool": t.name,
                                "result": text,
                            },
                            ensure_ascii=False,
                        )
                    except Exception as e:  # noqa: BLE001
                        return json.dumps(
                            {
                                "ok": False,
                                "server": c.name,
                                "tool": t.name,
                                "error": str(e),
                            },
                            ensure_ascii=False,
                        )

                return _handler

            reg.register(
                ToolSpec(
                    name=tool_name,
                    description=f"[MCP:{client.name}] {desc}",
                    parameters=schema if isinstance(schema, dict) else {"type": "object"},
                ),
                _make_handler(),
            )
            info["tools"].append(tool_name)

    def _list_mcp(args: dict[str, Any]) -> str:
        if not MCP_AVAILABLE:
            return json.dumps(
                {
                    "ok": False,
                    "error": (
                        "当前环境未安装 mcp SDK（需要 Python≥3.10："
                        "pip install 'tangyuan[mcp]'）。"
                    ),
                    "config": str(resolve_mcp_config(workspace)),
                },
                ensure_ascii=False,
            )
        payload: dict[str, Any] = {
            "ok": True,
            "servers": list(clients.keys()),
            "tools": info.get("tools") or [],
            "warnings": warnings,
            "config": info.get("config"),
        }
        if not clients and warnings:
            payload["ok"] = False
            payload["error"] = "；".join(warnings)
            return json.dumps(payload, ensure_ascii=False)

        lines = []
        for name, client in clients.items():
            try:
                tools = client.list_tools()
                lines.append(f"## {name} ({len(tools)} tools)")
                for t in tools:
                    lines.append(f"- {t.name}: {getattr(t, 'description', '') or ''}")
            except Exception as e:  # noqa: BLE001
                lines.append(f"## {name}\n错误: {e}")
        if warnings:
            lines.append("## warnings")
            lines.extend(f"- {w}" for w in warnings)
        payload["detail"] = "\n".join(lines) if lines else "(无)"
        return json.dumps(payload, ensure_ascii=False)

    if "list_mcp_servers" not in reg.names():
        reg.register(
            ToolSpec(
                name="list_mcp_servers",
                description="列出已连接的 MCP Server 及其工具（默认 time；有 Token 时含 github）。",
                parameters={
                    "type": "object",
                    "properties": {
                        "server": {
                            "type": "string",
                            "description": "可选：只看某一个 server",
                        }
                    },
                },
            ),
            _list_mcp,
        )

    return info
