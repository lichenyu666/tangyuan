from __future__ import annotations

from pathlib import Path
from typing import Optional

from tangyuan.agent.plan import TaskPlan
from tangyuan.config import Settings
from tangyuan.tools.context import ToolContext
from tangyuan.tools.register_fs import register_fs_tools
from tangyuan.tools.register_mcp import register_mcp_tools
from tangyuan.tools.register_memory import register_memory_tools, register_skill_tools
from tangyuan.tools.register_plan import register_plan_tools
from tangyuan.tools.register_shell import register_shell_tools
from tangyuan.tools.register_subagent import register_subagent_tools
from tangyuan.tools.register_team import ensure_team
from tangyuan.tools.register_web import register_office_tools, register_web_tools
from tangyuan.tools.registry import ConfirmFn, ToolRegistry


def build_default_tools(
    workspace: Path,
    shell_timeout: int = 60,
    confirm: Optional[ConfirmFn] = None,
    confirm_writes: bool = True,
    confirm_shell: bool = True,
    plan: Optional[TaskPlan] = None,
    settings: Optional[Settings] = None,
    enable_mcp: bool = True,
    enable_subagent: bool = True,
    enable_team: bool = True,
) -> ToolRegistry:
    """按职责注册全部内置工具。"""
    ctx = ToolContext(
        workspace=workspace,
        shell_timeout=shell_timeout,
        confirm=confirm,
        confirm_writes=confirm_writes,
        confirm_shell=confirm_shell,
    )
    reg = ToolRegistry()
    register_fs_tools(reg, ctx)
    register_shell_tools(reg, ctx)
    register_web_tools(reg, ctx)
    register_office_tools(reg, ctx)
    register_memory_tools(reg, ctx)
    register_skill_tools(reg, ctx)
    register_plan_tools(reg, plan if plan is not None else TaskPlan())
    if enable_mcp:
        register_mcp_tools(reg, workspace)
    if enable_subagent and settings is not None:
        register_subagent_tools(reg, settings=settings, parent_tools=reg)
    if enable_team and settings is not None:
        ensure_team(settings, reg)
    return reg
