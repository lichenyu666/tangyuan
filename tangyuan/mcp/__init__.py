"""MCP 客户端（stdio）+ 默认 time server 开箱配置。"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

MCP_AVAILABLE = True
try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
except ImportError:  # pragma: no cover
    MCP_AVAILABLE = False
    ClientSession = Any  # type: ignore
    StdioServerParameters = Any  # type: ignore
    stdio_client = None  # type: ignore


def _mcp_tool_name(server_name: str, mcp_name: str) -> str:
    sanitized = re.sub(r"[^a-zA-Z0-9_-]", "_", mcp_name)
    return f"mcp_{server_name}_{sanitized}"[:64]


def _result_to_text(result: Any) -> str:
    parts: list[str] = []
    content = getattr(result, "content", None) or []
    for block in content:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
        else:
            parts.append(str(block))
    if not parts and hasattr(result, "model_dump"):
        return json.dumps(result.model_dump(), ensure_ascii=False, default=str)
    return "\n".join(parts) if parts else str(result)


class MCPClient:
    def __init__(self, name: str, params: Any):
        self.name = name
        self.params = params
        self._tools: list | None = None

    async def _alist_tools(self) -> list:
        async with stdio_client(self.params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.list_tools()
                return list(result.tools)

    async def _acall_tool(self, name: str, arguments: dict[str, Any] | None) -> str:
        async with stdio_client(self.params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(name, arguments or {})
                return _result_to_text(result)

    def list_tools(self) -> list:
        if self._tools is None:
            self._tools = asyncio.run(self._alist_tools())
        return list(self._tools)

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> str:
        return asyncio.run(self._acall_tool(name, arguments))


def time_server_script() -> Path:
    return Path(__file__).resolve().parent / "servers" / "time_server.py"


def github_mcp_binary() -> Path:
    return Path.home() / ".tangyuan" / "bin" / "github-mcp-server"


def resolve_github_token() -> str:
    """从环境 / ~/.tangyuan/.env / gh auth token 解析 GitHub PAT。"""
    for key in (
        "GITHUB_PERSONAL_ACCESS_TOKEN",
        "GH_TOKEN",
        "GITHUB_TOKEN",
    ):
        val = (os.environ.get(key) or "").strip()
        if val:
            return val
    for path in (
        Path.home() / ".tangyuan" / ".env",
        Path.cwd() / ".env",
    ):
        if not path.is_file():
            continue
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k = k.strip()
                v = v.strip().strip("'").strip('"')
                if k in (
                    "GITHUB_PERSONAL_ACCESS_TOKEN",
                    "GH_TOKEN",
                    "GITHUB_TOKEN",
                ) and v:
                    return v
        except Exception:  # noqa: BLE001
            continue
    try:
        import subprocess

        proc = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            timeout=8,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    except Exception:  # noqa: BLE001
        pass
    return ""


def resolve_mcp_config(workspace: Path) -> Path:
    candidates = [
        workspace / ".tangyuan" / "mcp_servers.json",
        workspace / "mcp_servers.json",
        Path.home() / ".tangyuan" / "mcp_servers.json",
    ]
    for p in candidates:
        if p.is_file():
            return p
    return candidates[0]


def _default_servers() -> dict[str, Any]:
    servers: dict[str, Any] = {
        "time": {
            "enabled": True,
            "command": sys.executable,
            "args": [str(time_server_script())],
        }
    }
    gh_bin = github_mcp_binary()
    if gh_bin.is_file():
        servers["github"] = {
            "enabled": True,
            "command": str(gh_bin),
            "args": ["stdio"],
            "env": {
                # 实际 token 在连接时由 resolve_github_token() 注入，勿把密钥写进此文件
                "GITHUB_PERSONAL_ACCESS_TOKEN": ""
            },
        }
    return servers


def ensure_default_mcp_config(workspace: Path) -> Path:
    """确保有可用 MCP 配置：内置 time；若已安装 github-mcp-server 则加入 github。"""
    path = resolve_mcp_config(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    defaults = _default_servers()
    if not path.is_file():
        data = {"servers": defaults}
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return path
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        data = {"servers": {}}
    servers = data.setdefault("servers", {})
    changed = False
    for name, cfg in defaults.items():
        if name not in servers:
            servers[name] = cfg
            changed = True
        elif name == "github":
            # 补上二进制路径（若用户配置缺 command）
            if not servers[name].get("command") and cfg.get("command"):
                servers[name]["command"] = cfg["command"]
                servers[name].setdefault("args", ["stdio"])
                changed = True
    if changed:
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return path


def load_mcp_tool_map(
    workspace: Path,
) -> tuple[dict[str, tuple[MCPClient, Any]], dict[str, MCPClient], list[str]]:
    """返回 (tool_map, clients, warnings)。"""
    warnings: list[str] = []
    if not MCP_AVAILABLE:
        return {}, {}, ["未安装 mcp SDK"]
    path = ensure_default_mcp_config(workspace)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        return {}, {}, [f"读取 MCP 配置失败: {e}"]
    servers = data.get("servers") or {}
    tool_map: dict[str, tuple[MCPClient, Any]] = {}
    clients: dict[str, MCPClient] = {}
    token = resolve_github_token()
    for name, cfg in servers.items():
        if not cfg.get("enabled", True):
            continue
        command = cfg.get("command")
        if not command:
            continue
        if name == "github" and not token:
            warnings.append(
                "GitHub MCP 已配置但未找到 Token。"
                "请执行 `gh auth login`，或在 ~/.tangyuan/.env 写入 "
                "GITHUB_PERSONAL_ACCESS_TOKEN=你的PAT"
            )
            continue
        args = list(cfg.get("args") or [])
        fixed_args = []
        for a in args:
            p = Path(str(a))
            if not p.is_absolute():
                cand = (workspace / a).resolve()
                fixed_args.append(str(cand) if cand.exists() else str(a))
            else:
                fixed_args.append(str(a))
        env = dict(cfg.get("env") or {})
        if name == "github":
            env["GITHUB_PERSONAL_ACCESS_TOKEN"] = token
        env_full = {**os.environ, **env}
        params = StdioServerParameters(
            command=command, args=fixed_args, env=env_full
        )
        try:
            client = MCPClient(name, params)
            tools = client.list_tools()
            for tool in tools:
                tool_map[_mcp_tool_name(name, tool.name)] = (client, tool)
            clients[name] = client
        except Exception as e:  # noqa: BLE001
            warnings.append(f"MCP server '{name}' 启动失败: {e}")
            continue
    return tool_map, clients, warnings
