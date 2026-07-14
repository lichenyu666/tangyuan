"""Git 工具底层实现：在 workspace 下执行只读与写入 git 操作。

设计要点：
- 只在 workspace 是 git 仓库时才工作（首次调用时检测）。
- 写操作（commit / add）走 ToolContext 的 confirm 流程。
- 拒绝危险操作：force push 到 main / push --force-with-lease 到远端、reset --hard HEAD 等
  不在工具暴露的范围内（让模型走 run_shell 显式做）。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional


def _git_dir(workspace: Path) -> Optional[Path]:
    """返回 .git 路径；不是仓库返回 None。"""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    if proc.returncode != 0:
        return None
    p = (workspace / proc.stdout.strip()).resolve()
    return p if p.exists() else None


def is_git_repo(workspace: Path) -> bool:
    return _git_dir(workspace) is not None


def _run(workspace: Path, args: List[str], timeout: int = 15) -> Dict[str, Any]:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"git 超时({timeout}s)"}
    except FileNotFoundError:
        return {"ok": False, "error": "未找到 git 命令"}
    return {
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "stdout": (proc.stdout or "")[-8000:],
        "stderr": (proc.stderr or "")[-2000:],
    }


def git_status(workspace: Path, *, porcelain: bool = True) -> str:
    if not is_git_repo(workspace):
        return json.dumps({"ok": False, "error": "当前 workspace 不是 git 仓库"}, ensure_ascii=False)
    args = ["status"]
    if porcelain:
        args.append("--porcelain=v1")
        args.append("--branch")
    res = _run(workspace, args)
    return json.dumps(res, ensure_ascii=False)


def git_diff(workspace: Path, *, staged: bool = False, path: Optional[str] = None, max_lines: int = 200) -> str:
    if not is_git_repo(workspace):
        return json.dumps({"ok": False, "error": "当前 workspace 不是 git 仓库"}, ensure_ascii=False)
    args = ["diff"]
    if staged:
        args.append("--cached")
    if path:
        args += ["--", path]
    res = _run(workspace, args, timeout=20)
    out = res.get("stdout") or ""
    lines = out.splitlines()
    if len(lines) > max_lines:
        out = "\n".join(lines[:max_lines]) + f"\n…(diff truncated, {len(lines) - max_lines} more lines)"
        res["stdout"] = out
        res["truncated"] = True
    return json.dumps(res, ensure_ascii=False)


def git_log(workspace: Path, *, limit: int = 10, oneline: bool = True) -> str:
    if not is_git_repo(workspace):
        return json.dumps({"ok": False, "error": "当前 workspace 不是 git 仓库"}, ensure_ascii=False)
    args = ["log", f"-n{max(1, min(limit, 100))}"]
    if oneline:
        args.append("--oneline")
    res = _run(workspace, args)
    return json.dumps(res, ensure_ascii=False)


def git_add(workspace: Path, paths: List[str]) -> str:
    if not is_git_repo(workspace):
        return json.dumps({"ok": False, "error": "当前 workspace 不是 git 仓库"}, ensure_ascii=False)
    if not paths:
        return json.dumps({"ok": False, "error": "paths 为空"}, ensure_ascii=False)
    # 限定为 workspace 内的路径，防止绝对路径越界
    safe: List[str] = []
    for p in paths:
        if p in {".", "-A", "--all"}:
            safe.append("-A")
            continue
        rp = Path(p)
        if rp.is_absolute():
            try:
                rp = rp.relative_to(workspace.resolve())
            except ValueError:
                return json.dumps({"ok": False, "error": f"路径越界 workspace: {p}"}, ensure_ascii=False)
        safe.append(str(rp))
    res = _run(workspace, ["add", "--", *safe])
    return json.dumps(res, ensure_ascii=False)


def git_commit(workspace: Path, message: str, *, add_all: bool = False) -> str:
    if not is_git_repo(workspace):
        return json.dumps({"ok": False, "error": "当前 workspace 不是 git 仓库"}, ensure_ascii=False)
    if not message or not message.strip():
        return json.dumps({"ok": False, "error": "commit message 不能为空"}, ensure_ascii=False)
    args: List[str] = []
    if add_all:
        args = ["add", "-A"]
        _run(workspace, args)
    # 用 -F - 从 stdin 传 message，避免 shell 转义问题
    try:
        proc = subprocess.run(
            ["git", "commit", "-F", "-"],
            cwd=str(workspace),
            input=message,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except subprocess.TimeoutExpired:
        return json.dumps({"ok": False, "error": "git commit 超时"}, ensure_ascii=False)
    return json.dumps(
        {
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "stdout": (proc.stdout or "")[-2000:],
            "stderr": (proc.stderr or "")[-2000:],
            "message": message,
        },
        ensure_ascii=False,
    )


def git_show(workspace: Path, ref: str, *, max_lines: int = 200) -> str:
    """查看某个 commit 的内容（diff + message）。"""
    if not is_git_repo(workspace):
        return json.dumps({"ok": False, "error": "当前 workspace 不是 git 仓库"}, ensure_ascii=False)
    if not ref or not ref.strip():
        return json.dumps({"ok": False, "error": "ref 为空"}, ensure_ascii=False)
    res = _run(workspace, ["show", "--stat", "--patch", ref], timeout=20)
    out = res.get("stdout") or ""
    lines = out.splitlines()
    if len(lines) > max_lines:
        out = "\n".join(lines[:max_lines]) + f"\n…(show truncated, {len(lines) - max_lines} more lines)"
        res["stdout"] = out
        res["truncated"] = True
    return json.dumps(res, ensure_ascii=False)


def git_branch(workspace: Path) -> str:
    if not is_git_repo(workspace):
        return json.dumps({"ok": False, "error": "当前 workspace 不是 git 仓库"}, ensure_ascii=False)
    res = _run(workspace, ["branch", "--show-current"])
    return json.dumps(res, ensure_ascii=False)
