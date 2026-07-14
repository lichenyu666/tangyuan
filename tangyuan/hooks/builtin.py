"""内置 Hooks。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from tangyuan.hooks.base import Hook, HookDecision


class OutputTruncateHook(Hook):
    name = "output_truncate"
    matcher = "*"

    def __init__(self, max_chars: int = 12000):
        self.max_chars = max_chars

    def after_tool_call(self, ctx: dict[str, Any]) -> Any:
        output = ctx.get("output")
        if isinstance(output, str) and len(output) > self.max_chars:
            ctx["output"] = (
                output[: self.max_chars]
                + f"\n\n[... 输出已截断，原始 {len(output)} 字符，"
                f"保留前 {self.max_chars} 字符]"
            )
        return None


class ToolAuditHook(Hook):
    name = "tool_audit"
    matcher = "write_file|apply_patch|run_shell|move_to_trash"

    def __init__(self, path: Path | None = None):
        self.path = path

    def after_tool_call(self, ctx: dict[str, Any]) -> Any:
        if self.path is None:
            return None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            out = str(ctx.get("output", ""))
            record = {
                "ts": datetime.now().isoformat(timespec="seconds"),
                "tool": ctx.get("name"),
                "input": ctx.get("input"),
                "output_preview": out[:500],
            }
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        except Exception:  # noqa: BLE001
            pass
        return None


class PlanStopGateHook(Hook):
    """结束前检查未完成计划：有残单则 block，迫使继续执行。"""

    name = "plan_stop_gate"

    def on_stop(self, ctx: dict[str, Any]) -> Any:
        plan = ctx.get("plan")
        if plan is None:
            return None
        open_items = getattr(plan, "open_items", lambda: [])()
        if not open_items:
            return None
        lines = "\n".join(
            f"- [{i.status}] `{i.id}` {i.content}" for i in open_items
        )
        ctx["unfinished"] = open_items
        return HookDecision(
            action="block",
            reason=(
                "差事尚未办妥，以下任务仍未完成，请按计划继续执行，"
                "并按规矩用 update_plan 更新状态：\n" + lines
            ),
        )
