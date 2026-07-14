"""公开 Demo 工具集：只读 + 禁 shell / 写记忆 / 子代理 / Team / MCP。"""

from __future__ import annotations

from pathlib import Path

from tangyuan.config import Settings
from tangyuan.tools.default import build_default_tools
from tangyuan.tools.registry import ToolRegistry

# Demo 中明确卸掉的工具（即使 read_only 仍可能注册）
_DEMO_BLOCKLIST = (
    "run_shell",
    "open_path",
    "open_app",
    "move_to_trash",
    "remember",
    "write_file",
    "apply_patch",
    "create_pptx",
    "git_add",
    "git_commit",
    "dispatch_subagent",
    "spawn_teammate",
    "send_message",
    "read_inbox",
    "broadcast",
)


def build_demo_tools(
    workspace: Path,
    settings: Settings | None = None,
) -> ToolRegistry:
    """构建简历 Demo 用的白名单工具。"""
    reg = build_default_tools(
        workspace,
        shell_timeout=30,
        confirm=None,
        confirm_writes=False,
        confirm_shell=False,
        settings=settings,
        enable_mcp=False,
        enable_subagent=False,
        enable_team=False,
        enable_git=True,
        enable_semantic=False,
        read_only=True,
    )
    for name in _DEMO_BLOCKLIST:
        reg.unregister(name)
    # 卸掉可能由 MCP / team 动态挂上的名字
    for name in list(reg.names()):
        if name.startswith("mcp_") or name.startswith("team_"):
            reg.unregister(name)
    return reg
