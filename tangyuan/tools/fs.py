from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from tangyuan.tools.paths import any_existing_path, workspace_path

def list_dir(workspace: Path, rel: str) -> str:
    if rel in (".", ""):
        path = workspace.resolve()
    elif Path(rel).expanduser().is_absolute():
        path = any_existing_path(workspace, rel)
    else:
        path = workspace_path(workspace, rel)
        if not path.exists():
            return json.dumps({"ok": False, "error": "路径不存在"}, ensure_ascii=False)
    if not path.is_dir():
        return json.dumps({"ok": False, "error": "不是目录"}, ensure_ascii=False)
    items = []
    for p in sorted(path.iterdir())[:200]:
        items.append({"name": p.name, "type": "dir" if p.is_dir() else "file"})
    return json.dumps({"ok": True, "path": str(path), "items": items}, ensure_ascii=False)


def read_file(workspace: Path, rel: str, offset: int, limit: int) -> str:
    path = any_existing_path(workspace, rel)
    if not path.is_file():
        return json.dumps({"ok": False, "error": "不是文件"}, ensure_ascii=False)
    text = path.read_text(encoding="utf-8", errors="replace").splitlines()
    start = max(offset - 1, 0)
    end = min(start + max(limit, 1), len(text))
    chunk = text[start:end]
    numbered = [f"{i + start + 1:>4}| {line}" for i, line in enumerate(chunk)]
    return json.dumps(
        {
            "ok": True,
            "path": str(path),
            "total_lines": len(text),
            "offset": offset,
            "content": "\n".join(numbered),
        },
        ensure_ascii=False,
    )


def write_file(workspace: Path, rel: str, content: str) -> str:
    path = workspace_path(workspace, rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return json.dumps(
        {"ok": True, "path": str(path), "bytes": len(content.encode("utf-8"))},
        ensure_ascii=False,
    )


def apply_patch(
    workspace: Path,
    rel: str,
    old_string: str,
    new_string: str,
    *,
    replace_all: bool = False,
) -> str:
    if not old_string:
        return json.dumps(
            {"ok": False, "error": "old_string 不能为空；新建文件请用 write_file"},
            ensure_ascii=False,
        )
    path = workspace_path(workspace, rel)
    if not path.is_file():
        return json.dumps({"ok": False, "error": f"文件不存在: {rel}"}, ensure_ascii=False)
    text = path.read_text(encoding="utf-8", errors="replace")
    count = text.count(old_string)
    if count == 0:
        return json.dumps(
            {
                "ok": False,
                "error": "old_string 未匹配到任何内容；请先 read_file 确认原文",
                "path": str(path),
            },
            ensure_ascii=False,
        )
    if count > 1 and not replace_all:
        return json.dumps(
            {
                "ok": False,
                "error": f"old_string 匹配到 {count} 处；请扩大上下文使其唯一，或设 replace_all=true",
                "path": str(path),
                "matches": count,
            },
            ensure_ascii=False,
        )
    if replace_all:
        new_text = text.replace(old_string, new_string)
        replaced = count
    else:
        new_text = text.replace(old_string, new_string, 1)
        replaced = 1
    path.write_text(new_text, encoding="utf-8")
    return json.dumps(
        {
            "ok": True,
            "path": str(path),
            "replaced": replaced,
            "bytes": len(new_text.encode("utf-8")),
        },
        ensure_ascii=False,
    )


def search_text(
    workspace: Path,
    query: str,
    rel: str,
    max_hits: int,
    *,
    glob: Optional[str] = None,
    context: int = 0,
    use_regex: bool = True,
) -> str:
    if Path(rel).expanduser().is_absolute():
        root = Path(rel).expanduser().resolve()
    else:
        root = workspace_path(workspace, rel)

    rg = shutil.which("rg")
    if rg:
        return search_text_rg(
            workspace, rg, query, root, max_hits, glob=glob, context=context, use_regex=use_regex
        )
    return search_text_python(
        workspace, query, root, max_hits, glob=glob, context=context, use_regex=use_regex
    )


def search_text_rg(
    workspace: Path,
    rg: str,
    query: str,
    root: Path,
    max_hits: int,
    *,
    glob: Optional[str],
    context: int,
    use_regex: bool,
) -> str:
    cmd = [rg, "--line-number", "--no-heading", "--color", "never", "--hidden"]
    cmd += ["--glob", "!.git/**", "--glob", "!.venv/**", "--glob", "!node_modules/**", "--glob", "!.tangyuan/**"]
    if glob:
        cmd += ["--glob", glob]
    if context > 0:
        cmd += ["-C", str(context)]
    if not use_regex:
        cmd.append("--fixed-strings")
    cmd += ["--max-count", str(max(1, max_hits)), query, str(root)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return json.dumps({"ok": False, "error": "rg 搜索超时"}, ensure_ascii=False)
    # rg exit 1 = no matches
    if proc.returncode not in (0, 1):
        return json.dumps(
            {"ok": False, "error": (proc.stderr or "rg 失败")[:500], "engine": "rg"},
            ensure_ascii=False,
        )
    hits: List[Dict[str, Any]] = []
    for line in (proc.stdout or "").splitlines():
        if len(hits) >= max_hits:
            break
        # path:line:text  or context lines with -
        m = re.match(r"^(.*?):(\d+)([:-])(.*)$", line)
        if not m:
            continue
        p, ln, _sep, text = m.groups()
        try:
            show = str(Path(p).resolve().relative_to(workspace.resolve()))
        except ValueError:
            show = p
        hits.append({"path": show, "line": int(ln), "text": text[:240]})
    return json.dumps(
        {"ok": True, "hits": hits, "truncated": len(hits) >= max_hits, "engine": "rg"},
        ensure_ascii=False,
    )


def search_text_python(
    workspace: Path,
    query: str,
    root: Path,
    max_hits: int,
    *,
    glob: Optional[str],
    context: int,
    use_regex: bool,
) -> str:
    hits: List[Dict[str, Any]] = []
    skip_dirs = {".git", ".venv", "venv", "__pycache__", "node_modules", ".tangyuan"}
    try:
        matcher = re.compile(query) if use_regex else None
    except re.error as e:
        return json.dumps({"ok": False, "error": f"非法正则: {e}"}, ensure_ascii=False)

    def match_line(line: str) -> bool:
        if matcher is not None:
            return bool(matcher.search(line))
        return query in line

    paths: List[Path]
    if root.is_file():
        paths = [root]
    else:
        pattern = glob or "*"
        paths = [p for p in root.rglob(pattern) if p.is_file()]

    for p in paths:
        if any(part in skip_dirs for part in p.parts):
            continue
        try:
            lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines, 1):
            if not match_line(line):
                continue
            try:
                show = str(p.relative_to(workspace))
            except ValueError:
                show = str(p)
            snippet = line[:240]
            if context > 0:
                lo = max(0, i - 1 - context)
                hi = min(len(lines), i + context)
                snippet = "\n".join(lines[lo:hi])[:500]
            hits.append({"path": show, "line": i, "text": snippet})
            if len(hits) >= max_hits:
                return json.dumps(
                    {"ok": True, "hits": hits, "truncated": True, "engine": "python"},
                    ensure_ascii=False,
                )
    return json.dumps(
        {"ok": True, "hits": hits, "truncated": False, "engine": "python"},
        ensure_ascii=False,
    )

