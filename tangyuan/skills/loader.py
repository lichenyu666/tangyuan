from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional


def _has_skill_packages(root: Path) -> bool:
    if not root.is_dir():
        return False
    for d in root.iterdir():
        if d.is_dir() and (d / "SKILL.md").is_file():
            return True
    return False


def builtin_catalog() -> Path:
    return Path(__file__).resolve().parent / "catalog"


def skills_root(workspace: Path) -> Path:
    """
    加载顺序：
    1. <workspace>/skills/（含至少一个 */SKILL.md 时）
    2. 包内内置 catalog：tangyuan/skills/catalog/
    """
    local = workspace / "skills"
    if _has_skill_packages(local):
        return local
    return builtin_catalog()


def _title_from_body(body: str, fallback: str) -> str:
    for line in body.splitlines():
        if line.startswith("#"):
            return line.lstrip("#").strip() or fallback
    return fallback


def _when_to_use(body: str) -> str:
    """从 SKILL.md 抽出「何时使用」作为摘要；没有则退回首段非标题文字。"""
    lines = body.splitlines()
    collecting = False
    chunks: List[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("##"):
            if collecting:
                break
            if "何时使用" in stripped:
                collecting = True
            continue
        if collecting and stripped:
            chunks.append(stripped)
    if chunks:
        return " ".join(chunks)

    paras: List[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            if paras:
                break
            continue
        paras.append(stripped)
        if len(" ".join(paras)) > 120:
            break
    text = " ".join(paras).strip()
    return text[:160] + ("…" if len(text) > 160 else "") if text else "(无摘要)"


def list_skills(workspace: Path) -> List[Dict[str, str]]:
    root = skills_root(workspace)
    if not root.is_dir():
        return []
    items: List[Dict[str, str]] = []
    for d in sorted(root.iterdir()):
        if not d.is_dir():
            continue
        skill_md = d / "SKILL.md"
        if not skill_md.is_file():
            continue
        text = skill_md.read_text(encoding="utf-8", errors="replace")
        items.append(
            {
                "id": d.name,
                "title": _title_from_body(text, d.name),
                "when": _when_to_use(text),
                "path": str(skill_md),
                "body": text,
            }
        )
    return items


def load_skill_body(workspace: Path, skill_id: str) -> Optional[str]:
    for s in list_skills(workspace):
        if s["id"] == skill_id:
            return s["body"]
    return None


def build_skills_prompt_section(
    workspace: Path,
    forced_skill_id: Optional[str] = None,
) -> str:
    """
    渐进式披露：
    - 自动模式：系统提示只放 id / 标题 / 何时使用；全文需通过 load_skill 按需拉取。
    - 手动强制：用户 /skill <id> 时直接注入该 Skill 全文。
    """
    skills = list_skills(workspace)
    if not skills:
        return ""

    if forced_skill_id:
        body = load_skill_body(workspace, forced_skill_id)
        if not body:
            return f"（用户指定了 Skill `{forced_skill_id}`，但未找到对应 SKILL.md）\n"
        return (
            "## 当前强制使用的 Skill\n"
            f"用户通过 /skill {forced_skill_id} 指定。请严格按下列步骤执行：\n\n"
            f"{body}\n"
        )

    lines = [
        "## 可用 Skills（渐进式披露）",
        "下面只有目录摘要。若用户意图匹配某 Skill 的「何时使用」：",
        "1. 先调用工具 `load_skill`（传入 skill_id）拉取完整剧本；",
        "2. 再严格按剧本步骤执行。",
        "不匹配就不要硬套。用户也可用 `/skill <id>` 强制指定（此时全文已在系统提示中）。",
        "",
    ]
    for s in skills:
        lines.append(f"- `{s['id']}` — {s['title']}")
        lines.append(f"  何时使用：{s['when']}")
    lines.append("")
    return "\n".join(lines)
