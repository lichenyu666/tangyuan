from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional


def global_memory_dir() -> Path:
    """~/.tangyuan/memory/ — 全局记忆根目录。"""
    d = Path.home() / ".tangyuan" / "memory"
    d.mkdir(parents=True, exist_ok=True)
    return d


def project_memory_dir(workspace: Path) -> Path:
    """<workspace>/.tangyuan/memory/ — 项目记忆根目录。"""
    d = workspace.resolve() / ".tangyuan" / "memory"
    d.mkdir(parents=True, exist_ok=True)
    return d


def memory_md_path() -> Path:
    """全局长期记忆：MEMORY.md"""
    return global_memory_dir() / "MEMORY.md"


def project_memory_md_path(workspace: Path) -> Path:
    """项目长期记忆：workspace/.../MEMORY.md"""
    return project_memory_dir(workspace) / "MEMORY.md"


def history_path() -> Path:
    return global_memory_dir() / "history.jsonl"


def tokens_path() -> Path:
    return global_memory_dir() / "tokens.jsonl"


def daily_log_path(day: Optional[str] = None) -> Path:
    """按日日记：YYYY-MM-DD.md（本地日期）。"""
    if not day:
        day = datetime.now().strftime("%Y-%m-%d")
    return global_memory_dir() / f"{day}.md"


# ---- 兼容旧名 ----
def user_memory_path() -> Path:
    return memory_md_path()


def project_memory_path(workspace: Path) -> Path:
    return project_memory_md_path(workspace)
