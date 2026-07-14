from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class TraceLogger:
    """把每一步决策/工具调用落盘，方便复盘与面试讲解。"""

    def __init__(self, root: Path):
        self.dir = root / ".tangyuan" / "traces"
        self.dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.path = self.dir / f"run-{ts}.jsonl"
        self.events: list[dict[str, Any]] = []

    def log(self, kind: str, **payload: Any) -> None:
        event = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "kind": kind,
            **payload,
        }
        self.events.append(event)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def summary(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "steps": len([e for e in self.events if e["kind"] == "step"]),
            "tool_calls": len([e for e in self.events if e["kind"] == "tool_result"]),
            "errors": len([e for e in self.events if e["kind"] == "error"]),
        }
