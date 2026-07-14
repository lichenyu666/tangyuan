from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tangyuan.memory.paths import tokens_path


def append_tokens(
    *,
    model: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    workspace: str | None = None,
    kind: str = "chat",
    extra: dict[str, Any] | None = None,
) -> Path:
    """追加一条 token 用量到 tokens.jsonl。"""
    path = tokens_path()
    if total_tokens <= 0:
        total_tokens = prompt_tokens + completion_tokens
    row: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "kind": kind,
        "prompt_tokens": int(prompt_tokens or 0),
        "completion_tokens": int(completion_tokens or 0),
        "total_tokens": int(total_tokens or 0),
    }
    if workspace:
        row["workspace"] = workspace
    if extra:
        row.update(extra)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path


def record_usage_from_response(resp: Any, *, model: str, workspace: str | None = None) -> Path | None:
    """从 OpenAI ChatCompletion 响应提取 usage 并落盘。"""
    usage = getattr(resp, "usage", None)
    if usage is None:
        return None
    return append_tokens(
        model=model,
        prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
        completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
        total_tokens=getattr(usage, "total_tokens", 0) or 0,
        workspace=workspace,
        kind="chat",
    )


def summarize_tokens(limit_lines: int = 5000) -> dict[str, Any]:
    """汇总 tokens.jsonl（最近 limit_lines 行）。"""
    path = tokens_path()
    if not path.exists():
        return {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-limit_lines:]
    prompt = completion = total = calls = 0
    by_model: dict[str, int] = {}
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        calls += 1
        prompt += int(row.get("prompt_tokens") or 0)
        completion += int(row.get("completion_tokens") or 0)
        total += int(row.get("total_tokens") or 0)
        m = row.get("model") or "?"
        by_model[m] = by_model.get(m, 0) + int(row.get("total_tokens") or 0)
    return {
        "calls": calls,
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total,
        "by_model": by_model,
        "path": str(path),
    }
