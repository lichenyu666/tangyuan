from __future__ import annotations

from pathlib import Path


def workspace_path(workspace: Path, rel: str) -> Path:
    target = (workspace / rel).resolve()
    ws = workspace.resolve()
    if not str(target).startswith(str(ws)):
        raise ValueError(f"路径越界，禁止访问 workspace 外: {rel}")
    return target


def any_existing_path(workspace: Path, raw: str) -> Path:
    """允许绝对路径（用户拖入的文件）；相对路径仍相对 workspace。"""
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = (workspace / p).resolve()
    else:
        p = p.resolve()
    if not p.exists():
        raise FileNotFoundError(f"路径不存在: {raw}")
    return p
