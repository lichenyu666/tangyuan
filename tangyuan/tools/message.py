from __future__ import annotations

import re
from pathlib import Path
from typing import List, Tuple

def extract_attachments(user_text: str, workspace: Path) -> Tuple[str, List[Path]]:
    """支持 @path 与拖入的绝对路径（终端拖文件会粘贴路径）。"""
    paths: List[Path] = []
    # @file or @"path with spaces"
    for m in re.finditer(r'@(?:"([^"]+)"|(\S+))', user_text):
        raw = m.group(1) or m.group(2)
        p = Path(raw).expanduser()
        if not p.is_absolute():
            p = (workspace / p).resolve()
        if p.exists() and p.is_file():
            paths.append(p)

    # 裸绝对路径
    for m in re.finditer(r"(/(?:Users|home|tmp|var|opt)[^\s]+)", user_text):
        p = Path(m.group(1).rstrip("，。,.）)"))
        if p.exists() and p.is_file() and p not in paths:
            paths.append(p)

    # 去重
    uniq: List[Path] = []
    for p in paths:
        if p not in uniq:
            uniq.append(p)
    return user_text, uniq[:10]


def build_user_message(task: str, workspace: Path) -> str:
    text, files = extract_attachments(task, workspace)
    parts = [f"Workspace: {workspace.resolve()}", f"用户: {text}"]
    for f in files:
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            parts.append(f"\n[附件无法读取] {f}: {e}")
            continue
        if len(content) > 12000:
            content = content[:12000] + "\n...<truncated>"
        parts.append(f"\n[附件] {f}\n```\n{content}\n```")
    if files:
        parts.append("\n（已自动附带上述文件内容，可直接基于附件完成任务。）")
    return "\n".join(parts)

