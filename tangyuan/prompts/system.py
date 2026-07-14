from __future__ import annotations

from pathlib import Path
from typing import Optional

_PROMPTS_DIR = Path(__file__).resolve().parent


def _read_prompt(name: str) -> str:
    path = _PROMPTS_DIR / name
    if not path.is_file():
        raise FileNotFoundError(f"缺少提示词文件: {path}")
    return path.read_text(encoding="utf-8").strip()


def load_soul() -> str:
    """Soul：性格、价值观、说话方式。"""
    return _read_prompt("SOUL.md")


def load_system_ops() -> str:
    """System：工具、安全、Skills、记忆等操作规范。"""
    return _read_prompt("system.md")


def load_workspace_prompt() -> str:
    """Workspace：工作位置与读写边界。"""
    return _read_prompt("workspace.md")


def load_compact_prompt() -> str:
    """上下文压缩器用的 system 提示词。"""
    return _read_prompt("compact.md")


def load_distill_prompt() -> str:
    """项目记忆蒸馏用的 system 提示词。"""
    return _read_prompt("distill.md")


def build_base_system_prompt(
    soul: Optional[str] = None,
    ops: Optional[str] = None,
    workspace: Optional[str] = None,
) -> str:
    """组装基础系统提示 = Soul + 操作规范 + 工作区（不含动态 memory/skills）。"""
    parts = [
        (soul if soul is not None else load_soul()).strip(),
        (ops if ops is not None else load_system_ops()).strip(),
        (workspace if workspace is not None else load_workspace_prompt()).strip(),
    ]
    return "\n\n---\n\n".join(parts)


# 兼容旧导入名：启动时组装一次
SYSTEM_PROMPT = build_base_system_prompt()
