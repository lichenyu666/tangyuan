"""结构化任务计划：复杂任务用清单推进，避免对话里「口头计划」丢失后空转。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Literal, Optional

PlanStatus = Literal["pending", "in_progress", "completed", "cancelled"]
VALID_STATUSES = frozenset({"pending", "in_progress", "completed", "cancelled"})


@dataclass
class PlanItem:
    id: str
    content: str
    status: PlanStatus = "pending"

    def to_dict(self) -> Dict[str, str]:
        return asdict(self)


@dataclass
class TaskPlan:
    """会话内任务板（不持久化；/clear 或新 Agent 会清空）。"""

    items: List[PlanItem] = field(default_factory=list)

    def clear(self) -> None:
        self.items = []

    def to_dicts(self) -> List[Dict[str, str]]:
        return [i.to_dict() for i in self.items]

    def replace(self, raw_items: List[Dict[str, Any]]) -> Dict[str, Any]:
        parsed, err = _parse_items(raw_items)
        if err:
            return {"ok": False, "error": err}
        self.items = parsed
        return self._ok_payload("replaced")

    def merge(self, raw_items: List[Dict[str, Any]]) -> Dict[str, Any]:
        parsed, err = _parse_items(raw_items)
        if err:
            return {"ok": False, "error": err}
        by_id = {i.id: i for i in self.items}
        for item in parsed:
            by_id[item.id] = item
        order = [i.id for i in self.items]
        for item in parsed:
            if item.id not in order:
                order.append(item.id)
        merged = [by_id[i] for i in order if i in by_id]
        if sum(1 for i in merged if i.status == "in_progress") > 1:
            return {
                "ok": False,
                "error": "合并后出现多个 in_progress；同时只能有一个进行中的步骤",
                "plan": self.to_dicts(),
            }
        self.items = merged
        return self._ok_payload("merged")

    def open_items(self) -> List[PlanItem]:
        return [i for i in self.items if i.status in ("pending", "in_progress")]

    def progress_key(self) -> tuple:
        """快照：完成/取消集合 + 进行中，用于判断是否有实质进展。"""
        completed = tuple(sorted(i.id for i in self.items if i.status == "completed"))
        cancelled = tuple(sorted(i.id for i in self.items if i.status == "cancelled"))
        in_prog = tuple(i.id for i in self.items if i.status == "in_progress")
        pending = tuple(i.id for i in self.items if i.status == "pending")
        return (completed, cancelled, in_prog, pending)

    def render_open_digest(self) -> str:
        open_items = self.open_items()
        if not open_items:
            return "(无未完成项)"
        return " | ".join(f"{i.status}:{i.id}:{i.content}" for i in open_items)

    def _ok_payload(self, action: str) -> Dict[str, Any]:
        return {
            "ok": True,
            "action": action,
            "plan": self.to_dicts(),
            "summary": self.render_digest(),
            "open": self.render_open_digest(),
        }

    def render_prompt_section(self) -> str:
        if not self.items:
            return ""
        lines = [
            "## 当前任务计划（会话内）",
            "按状态推进；完成后勾 completed，卡住先改计划再换路径。",
            "",
        ]
        for item in self.items:
            mark = {
                "pending": "[ ]",
                "in_progress": "[>]",
                "completed": "[x]",
                "cancelled": "[-]",
            }.get(item.status, "[ ]")
            lines.append(f"- {mark} `{item.id}` {item.content} ({item.status})")
        return "\n".join(lines)

    def render_digest(self) -> str:
        if not self.items:
            return "(空)"
        parts = []
        for item in self.items:
            parts.append(f"{item.status}:{item.id}:{item.content}")
        return " | ".join(parts)


def _parse_items(raw_items: List[Dict[str, Any]]) -> tuple[List[PlanItem], Optional[str]]:
    if not isinstance(raw_items, list) or not raw_items:
        return [], "items 必须是非空数组"
    parsed: List[PlanItem] = []
    seen: set[str] = set()
    in_progress = 0
    for i, raw in enumerate(raw_items):
        if not isinstance(raw, dict):
            return [], f"items[{i}] 必须是对象"
        item_id = str(raw.get("id") or "").strip()
        content = str(raw.get("content") or "").strip()
        status = str(raw.get("status") or "pending").strip()
        if not item_id:
            return [], f"items[{i}] 缺少 id"
        if item_id in seen:
            return [], f"重复的 id: {item_id}"
        if not content:
            return [], f"items[{i}] 缺少 content"
        if status not in VALID_STATUSES:
            return [], f"非法 status `{status}`，允许: {sorted(VALID_STATUSES)}"
        if status == "in_progress":
            in_progress += 1
        seen.add(item_id)
        parsed.append(PlanItem(id=item_id, content=content, status=status))  # type: ignore[arg-type]
    if in_progress > 1:
        return [], "同时只能有一个 in_progress 步骤"
    return parsed, None
