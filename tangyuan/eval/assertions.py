"""评测断言原语：返回 (passed: bool, detail: str)。"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, List


@dataclass
class AssertResult:
    ok: bool
    detail: str = ""


def file_exists(ws: Path, path: str) -> AssertResult:
    p = ws / path
    if p.is_file():
        return AssertResult(True, f"{path} 存在")
    return AssertResult(False, f"{path} 不存在")


def file_not_exists(ws: Path, path: str) -> AssertResult:
    p = ws / path
    if not p.exists():
        return AssertResult(True, f"{path} 不存在")
    return AssertResult(False, f"{path} 仍存在")


def file_contains(ws: Path, path: str, text: str) -> AssertResult:
    p = ws / path
    if not p.is_file():
        return AssertResult(False, f"{path} 不存在")
    content = p.read_text(encoding="utf-8", errors="replace")
    if text in content:
        return AssertResult(True, f"{path} 含目标文本")
    snippet = content[:200].replace("\n", " ")
    return AssertResult(False, f"{path} 不含目标文本；前 200 字：{snippet}")


def file_not_contains(ws: Path, path: str, text: str) -> AssertResult:
    p = ws / path
    if not p.is_file():
        return AssertResult(True, f"{path} 不存在（视为通过）")
    content = p.read_text(encoding="utf-8", errors="replace")
    if text not in content:
        return AssertResult(True, f"{path} 不含禁词")
    return AssertResult(False, f"{path} 仍含禁词：{text}")


def shell_succeeds(ws: Path, cmd: str, timeout: int = 15) -> AssertResult:
    try:
        proc = subprocess.run(
            cmd, shell=True, cwd=str(ws), capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return AssertResult(False, f"超时：{cmd}")
    if proc.returncode == 0:
        return AssertResult(True, f"exit 0: {cmd}")
    return AssertResult(False, f"exit={proc.returncode} stderr={proc.stderr[:200]}")


def shell_output_contains(ws: Path, cmd: str, text: str, timeout: int = 15) -> AssertResult:
    try:
        proc = subprocess.run(
            cmd, shell=True, cwd=str(ws), capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return AssertResult(False, f"超时：{cmd}")
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    if text in out:
        return AssertResult(True, f"输出含目标文本")
    return AssertResult(False, f"输出不含 {text!r}；前 200 字：{out[:200]}")


def reply_contains(reply: str, text: str) -> AssertResult:
    if text in reply:
        return AssertResult(True, f"回复含目标文本")
    return AssertResult(False, f"回复不含 {text!r}；前 200 字：{reply[:200]}")


def reply_not_contains(reply: str, text: str) -> AssertResult:
    if text not in reply:
        return AssertResult(True, f"回复不含禁词")
    return AssertResult(False, f"回复仍含禁词：{text}")


def reply_any(reply: str, options: List[str]) -> AssertResult:
    for opt in options:
        if opt in reply:
            return AssertResult(True, f"回复命中 {opt!r}")
    return AssertResult(False, f"回复未命中任一关键词：{options}")


# 断言函数签名：接受 (workspace, reply) 返回 AssertResult
Assertion = Callable[[Path, str], AssertResult]


def make_file_exists(path: str) -> Assertion:
    def f(ws: Path, reply: str) -> AssertResult:
        return file_exists(ws, path)
    return f


def make_file_not_exists(path: str) -> Assertion:
    def f(ws: Path, reply: str) -> AssertResult:
        return file_not_exists(ws, path)
    return f


def make_file_contains(path: str, text: str) -> Assertion:
    def f(ws: Path, reply: str) -> AssertResult:
        return file_contains(ws, path, text)
    return f


def make_file_not_contains(path: str, text: str) -> Assertion:
    def f(ws: Path, reply: str) -> AssertResult:
        return file_not_contains(ws, path, text)
    return f


def make_shell_succeeds(cmd: str, timeout: int = 15) -> Assertion:
    def f(ws: Path, reply: str) -> AssertResult:
        return shell_succeeds(ws, cmd, timeout=timeout)
    return f


def make_shell_output_contains(cmd: str, text: str, timeout: int = 15) -> Assertion:
    def f(ws: Path, reply: str) -> AssertResult:
        return shell_output_contains(ws, cmd, text, timeout=timeout)
    return f


def make_reply_contains(text: str) -> Assertion:
    def f(ws: Path, reply: str) -> AssertResult:
        return reply_contains(reply, text)
    return f


def make_reply_not_contains(text: str) -> Assertion:
    def f(ws: Path, reply: str) -> AssertResult:
        return reply_not_contains(reply, text)
    return f


def make_reply_any(options: List[str]) -> Assertion:
    def f(ws: Path, reply: str) -> AssertResult:
        return reply_any(reply, options)
    return f
