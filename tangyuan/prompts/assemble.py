"""组装完整 system prompt：静态模板 + 动态 memory/skills/plan/repomap。"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from tangyuan.memory import build_memory_prompt_section
from tangyuan.prompts.system import build_base_system_prompt
from tangyuan.skills import build_skills_prompt_section
from tangyuan.tools.repomap import cache_repo_map

if TYPE_CHECKING:
    from tangyuan.agent.plan import TaskPlan


def assemble_system_prompt(
    workspace: Path,
    *,
    forced_skill_id: str | None = None,
    plan: TaskPlan | None = None,
) -> str:
    """
    全量系统提示拼装入口（Agent 只应调用这里）。

    顺序：
    1. Soul + system + workspace（静态 md）
    2. 长期记忆动态段
    3. Skills 渐进披露动态段
    4. Repo Map（符号级摘要，TTL 10 分钟缓存）
    5. 当前任务计划（若有）
    """
    parts = [build_base_system_prompt()]
    memory = build_memory_prompt_section(workspace)
    if memory:
        parts.append(memory.strip())
    skills = build_skills_prompt_section(workspace, forced_skill_id=forced_skill_id)
    if skills:
        parts.append(skills.strip())
    repo_map = cache_repo_map(workspace)
    if repo_map:
        parts.append(repo_map.strip())
    if plan is not None:
        plan_section = plan.render_prompt_section()
        if plan_section:
            parts.append(plan_section.strip())
    return "\n\n".join(parts)
