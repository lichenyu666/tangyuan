from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from tangyuan.memory.paths import (
    daily_log_path,
    global_memory_dir,
    memory_md_path,
    project_memory_dir,
    project_memory_md_path,
    user_memory_path,
    project_memory_path,
)

PROFILE_PROMPT_MAX_CHARS = 1800


def _default_memory_md() -> str:
    return (
        "# MEMORY.md — 全局长期记忆\n\n"
        "> 跨目录生效。稳定事实用 topic 覆盖更新。\n"
        "> 同目录还有：`YYYY-MM-DD.md`（日记）、`history.jsonl`、`tokens.jsonl`。\n\n"
        "## 基本信息\n"
        "- （还没有）\n\n"
        "## 偏好\n"
        "- 希望用大白话解释，少用专业黑话\n"
    )


def _default_project_md(workspace: Path) -> str:
    return (
        f"# MEMORY.md — 项目记忆（{workspace.resolve().name}）\n\n"
        "> 仅当前 workspace。约定、坑点、上次结论写这里。\n"
        "> 系统提示默认不塞全文，需要时 recall_memory(bucket=project)。\n\n"
    )


def _migrate_legacy(workspace: Path) -> None:
    """user.md / project.md → MEMORY.md；workspace 旧 user 迁到全局。"""
    gdir = global_memory_dir()
    legacy_global_user = gdir / "user.md"
    target = memory_md_path()
    if legacy_global_user.is_file() and not target.exists():
        legacy_global_user.rename(target)
    elif legacy_global_user.is_file() and target.exists():
        # 已有 MEMORY.md：把旧内容追加一次后改名备份
        bak = gdir / "user.md.bak"
        if not bak.exists():
            legacy_global_user.rename(bak)

    # workspace 旧 user.md → 全局 MEMORY（仅当全局几乎为空）
    legacy_ws_user = workspace.resolve() / ".tangyuan" / "memory" / "user.md"
    if legacy_ws_user.is_file():
        if not target.exists() or len(target.read_text(encoding="utf-8", errors="replace").strip()) < 80:
            text = legacy_ws_user.read_text(encoding="utf-8", errors="replace").strip()
            body = re.sub(r"^#\s*.*\n+", "", text).strip()
            target.write_text(
                "# MEMORY.md — 全局长期记忆\n\n> 已从旧版迁移。\n\n" + body + "\n",
                encoding="utf-8",
            )
        bak = legacy_ws_user.with_suffix(".md.bak")
        if not bak.exists():
            try:
                legacy_ws_user.rename(bak)
            except OSError:
                pass

    # project.md → MEMORY.md
    pdir = project_memory_dir(workspace)
    legacy_project = pdir / "project.md"
    proj_target = project_memory_md_path(workspace)
    if legacy_project.is_file() and not proj_target.exists():
        legacy_project.rename(proj_target)
    elif legacy_project.is_file() and proj_target.exists():
        bak = pdir / "project.md.bak"
        if not bak.exists():
            try:
                legacy_project.rename(bak)
            except OSError:
                pass


def ensure_memory_files(workspace: Path) -> None:
    _migrate_legacy(workspace)
    mp = memory_md_path()
    if not mp.exists():
        mp.write_text(_default_memory_md(), encoding="utf-8")
    pp = project_memory_md_path(workspace)
    if not pp.exists():
        pp.write_text(_default_project_md(workspace), encoding="utf-8")
    # 确保 jsonl 文件存在
    from tangyuan.memory.paths import history_path, tokens_path

    for p in (history_path(), tokens_path()):
        if not p.exists():
            p.write_text("", encoding="utf-8")
    # 今日日记抬头
    day = daily_log_path()
    if not day.exists():
        day.write_text(
            f"# {day.stem} 日记\n\n> 当日过程记录；稳定事实请写入 MEMORY.md。\n\n",
            encoding="utf-8",
        )


def ensure_default_user_memory(workspace: Path) -> Path:
    ensure_memory_files(workspace)
    return memory_md_path()


def read_user_profile() -> str:
    path = memory_md_path()
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace").strip()


def read_project_notes(workspace: Path) -> str:
    path = project_memory_md_path(workspace)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace").strip()


def read_daily_log(day: Optional[str] = None) -> str:
    path = daily_log_path(day)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace").strip()


def append_daily_log(text: str, *, heading: Optional[str] = None) -> str:
    """追加到今日 YYYY-MM-DD.md。"""
    text = text.strip()
    if not text:
        return "空内容"
    path = daily_log_path()
    if not path.exists():
        path.write_text(f"# {path.stem} 日记\n\n", encoding="utf-8")
    ts = datetime.now().strftime("%H:%M")
    block = f"\n### {ts}" + (f" {heading}" if heading else "") + f"\n{text}\n"
    with path.open("a", encoding="utf-8") as f:
        f.write(block)
    return f"已写入日记 → {path}"


def read_long_term_memory(workspace: Path) -> str:
    ensure_memory_files(workspace)
    parts: List[str] = []
    user = read_user_profile()
    if user:
        parts.append(user)
    proj = read_project_notes(workspace)
    if proj:
        parts.append(proj)
    daily = read_daily_log()
    if daily:
        parts.append(daily)
    return "\n\n---\n\n".join(parts)


def _upsert_line(path: Path, fact: str, topic: str) -> str:
    text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    new_line = f"- **{topic}**: {fact} ({ts})"
    pattern = re.compile(rf"(?m)^-\s*\*\*{re.escape(topic)}\*\*:.*$")
    if pattern.search(text):
        text = pattern.sub(new_line, text, count=1)
        path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
        return f"已更新 [{topic}] → {path}"
    with path.open("a", encoding="utf-8") as f:
        f.write(f"\n{new_line}\n")
    return f"已写入 [{topic}] → {path}"


def write_memory(
    workspace: Path,
    fact: str,
    *,
    bucket: str = "user",
    topic: Optional[str] = None,
) -> str:
    """
    bucket:
      - user / memory → 全局 MEMORY.md
      - project → 项目 MEMORY.md
      - daily → 今日 YYYY-MM-DD.md
    """
    fact = fact.strip()
    if not fact:
        return "空内容，未写入"
    ensure_memory_files(workspace)
    bucket = (bucket or "user").strip().lower()
    if bucket in {"notes", "profile", "memory"}:
        bucket = "user"

    if bucket == "daily":
        return append_daily_log(fact, heading=topic)

    if bucket == "user":
        path = memory_md_path()
    elif bucket == "project":
        path = project_memory_md_path(workspace)
    else:
        return f"未知 bucket: {bucket}（用 user / project / daily）"

    if topic:
        return _upsert_line(path, fact, topic.strip())

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    with path.open("a", encoding="utf-8") as f:
        f.write(f"\n- ({ts}) {fact}\n")
    return f"已追加 → {path}"


def append_memory(workspace: Path, text: str, *, to: str = "user") -> str:
    bucket = "project" if to == "project" else "user"
    if to == "daily":
        bucket = "daily"
    return write_memory(workspace, text, bucket=bucket)


def recall_memory(
    workspace: Path,
    *,
    bucket: str = "all",
    query: Optional[str] = None,
    max_chars: int = 6000,
) -> Dict[str, str]:
    ensure_memory_files(workspace)
    bucket = (bucket or "all").strip().lower()
    q = (query or "").strip().lower()

    sections: Dict[str, str] = {}
    if bucket in {"user", "all", "profile", "memory"}:
        sections["MEMORY.md"] = read_user_profile()
    if bucket in {"project", "all"}:
        sections["project/MEMORY.md"] = read_project_notes(workspace)
    if bucket in {"daily", "all"}:
        sections["daily"] = read_daily_log()

    if q:
        filtered: Dict[str, str] = {}
        for name, body in sections.items():
            hit_lines = [ln for ln in body.splitlines() if q in ln.lower()]
            if hit_lines:
                headers = [ln for ln in body.splitlines() if ln.startswith("#")][:2]
                filtered[name] = "\n".join(headers + [""] + hit_lines)
        sections = filtered

    out: Dict[str, str] = {}
    remaining = max_chars
    for name, body in sections.items():
        if remaining <= 0:
            out[name] = "(已达召回长度上限，请缩小 query)"
            break
        if len(body) <= remaining:
            out[name] = body
            remaining -= len(body)
        else:
            out[name] = body[:remaining] + "\n…(truncated)"
            remaining = 0
    return out


def build_memory_prompt_section(workspace: Path) -> str:
    ensure_memory_files(workspace)
    profile = read_user_profile()
    if len(profile) > PROFILE_PROMPT_MAX_CHARS:
        profile = (
            profile[:PROFILE_PROMPT_MAX_CHARS]
            + "\n…(MEMORY.md 过长已截断；完整请 recall_memory bucket=user)"
        )

    project_path = project_memory_md_path(workspace)
    has_project = project_path.exists() and len(read_project_notes(workspace)) > 80
    daily = daily_log_path()

    parts = [
        "## 长期记忆（工程化目录）",
        f"- 全局目录：`{global_memory_dir()}`",
        "  - `MEMORY.md` 稳定画像（下方常驻）",
        "  - `YYYY-MM-DD.md` 当日过程",
        "  - `history.jsonl` 对话历史",
        "  - `tokens.jsonl` Token 计量",
        f"- 项目：`{project_path}`（默认不塞全文，用 recall_memory）",
        "",
        "### MEMORY.md（常驻）",
        profile or "(空)",
        "",
        f"### 今日日记：`{daily.name}`",
        "过程记录写入日记；稳定事实写入 MEMORY.md。",
    ]
    if has_project:
        parts.extend(
            [
                "",
                "### 项目 MEMORY",
                f"存在项目记忆。相关约定请先 `recall_memory(bucket=\"project\")`。",
            ]
        )
    return "\n".join(parts) + "\n"


def estimate_messages_chars(messages: List[dict]) -> int:
    n = 0
    for m in messages:
        c = m.get("content")
        if isinstance(c, str):
            n += len(c)
        tc = m.get("tool_calls")
        if tc:
            n += len(str(tc))
    return n
