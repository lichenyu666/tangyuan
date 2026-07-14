"""公开 Demo 工具白名单单测：确保危险工具确实被卸载。"""

from __future__ import annotations

from pathlib import Path

from tangyuan.web.demo_tools import _DEMO_BLOCKLIST, build_demo_tools


def test_demo_blocklist_tools_absent(tmp_path: Path) -> None:
    reg = build_demo_tools(tmp_path, settings=None)
    names = set(reg.names())
    for banned in _DEMO_BLOCKLIST:
        assert banned not in names, f"{banned} 不应出现在公开 Demo"


def test_demo_no_shell_or_write(tmp_path: Path) -> None:
    reg = build_demo_tools(tmp_path, settings=None)
    names = set(reg.names())
    assert "run_shell" not in names
    assert "write_file" not in names
    assert "apply_patch" not in names


def test_demo_keeps_read_only_tools(tmp_path: Path) -> None:
    reg = build_demo_tools(tmp_path, settings=None)
    names = set(reg.names())
    assert "read_file" in names
    assert "list_dir" in names


def test_demo_has_no_mcp_or_team_tools(tmp_path: Path) -> None:
    reg = build_demo_tools(tmp_path, settings=None)
    for name in reg.names():
        assert not name.startswith("mcp_")
        assert not name.startswith("team_")
