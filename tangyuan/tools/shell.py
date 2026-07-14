from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

SHELL_BLOCK_PATTERNS = [
    (re.compile(r"rm\s+(-[a-zA-Z]*\s+)*/\s*$"), "禁止删除根目录"),
    (re.compile(r"rm\s+(-[a-zA-Z]*\s+)*~(/|\s|$)"), "禁止删除家目录"),
    (re.compile(r"\bmkfs\b"), "禁止 mkfs"),
    (re.compile(r"\bdd\b.*\bof=/dev/"), "禁止向块设备 dd"),
    (re.compile(r">\s*/dev/sd"), "禁止写入磁盘设备"),
    (re.compile(r"curl\s+[^\n|]*\|\s*(ba)?sh"), "禁止 curl|sh"),
    (re.compile(r"wget\s+[^\n|]*\|\s*(ba)?sh"), "禁止 wget|sh"),
    (re.compile(r":\(\)\s*\{\s*:\|:&\s*\};?:"), "禁止 fork 炸弹"),
]


def shell_blocked_reason(command: str) -> str | None:
    cmd = command.strip()
    if not cmd:
        return "空命令"
    for pat, reason in SHELL_BLOCK_PATTERNS:
        if pat.search(cmd):
            return f"危险命令已拒绝：{reason}"
    return None


def run_shell(workspace: Path, command: str, timeout: int) -> str:
    if not command.strip():
        return json.dumps({"ok": False, "error": "空命令"}, ensure_ascii=False)
    blocked = shell_blocked_reason(command)
    if blocked:
        return json.dumps({"ok": False, "error": blocked}, ensure_ascii=False)
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return json.dumps({"ok": False, "error": f"超时({timeout}s)"}, ensure_ascii=False)
    return json.dumps(
        {
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "stdout": (proc.stdout or "")[-8000:],
            "stderr": (proc.stderr or "")[-4000:],
        },
        ensure_ascii=False,
    )


def open_path(path: str) -> str:
    if sys.platform != "darwin":
        return json.dumps({"ok": False, "error": "当前仅实现了 macOS open"}, ensure_ascii=False)
    proc = subprocess.run(["open", path], capture_output=True, text=True)
    return json.dumps(
        {"ok": proc.returncode == 0, "stderr": proc.stderr, "path": path},
        ensure_ascii=False,
    )


def open_app(name: str) -> str:
    if sys.platform != "darwin":
        return json.dumps({"ok": False, "error": "当前仅实现了 macOS open -a"}, ensure_ascii=False)
    proc = subprocess.run(["open", "-a", name], capture_output=True, text=True)
    return json.dumps(
        {"ok": proc.returncode == 0, "stderr": proc.stderr, "app": name},
        ensure_ascii=False,
    )


def move_to_trash(path: str) -> str:
    if sys.platform != "darwin":
        return json.dumps({"ok": False, "error": "当前仅实现了 macOS 废纸篓"}, ensure_ascii=False)
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return json.dumps({"ok": False, "error": "路径不存在"}, ensure_ascii=False)
    script = f'tell application "Finder" to delete POSIX file "{p}"'
    proc = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    return json.dumps(
        {"ok": proc.returncode == 0, "stderr": proc.stderr, "path": str(p)},
        ensure_ascii=False,
    )

