"""记忆路径逻辑单测（用临时 HOME / workspace，不污染真实目录）。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from tangyuan.memory import paths


def test_project_memory_dir_under_workspace(tmp_path: Path) -> None:
    ws = tmp_path / "repo"
    ws.mkdir()
    d = paths.project_memory_dir(ws)
    assert d == ws.resolve() / ".tangyuan" / "memory"
    assert d.is_dir()


def test_project_memory_md_path(tmp_path: Path) -> None:
    ws = tmp_path / "repo"
    ws.mkdir()
    p = paths.project_memory_md_path(ws)
    assert p.name == "MEMORY.md"
    assert p.parent == ws.resolve() / ".tangyuan" / "memory"


def test_daily_log_filename_format(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    p = paths.daily_log_path("2026-07-14")
    assert p.name == "2026-07-14.md"
    assert p.parent == tmp_path / ".tangyuan" / "memory"


def test_daily_log_defaults_to_today(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    p = paths.daily_log_path()
    assert p.name == f"{datetime.now():%Y-%m-%d}.md"


def test_global_paths_names(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert paths.memory_md_path().name == "MEMORY.md"
    assert paths.history_path().name == "history.jsonl"
    assert paths.tokens_path().name == "tokens.jsonl"


def test_legacy_aliases(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    ws = tmp_path / "repo"
    ws.mkdir()
    assert paths.user_memory_path() == paths.memory_md_path()
    assert paths.project_memory_path(ws) == paths.project_memory_md_path(ws)
