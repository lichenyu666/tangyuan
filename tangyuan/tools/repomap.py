"""Repo Map：基于正则的符号级仓库摘要。

设计：
- 用正则提取主流语言的符号（class / function / def / method / struct / interface / enum）
- 输出每个文件路径 + 符号签名（简短）
- 控制总长度，可注入 system prompt
- 不依赖 tree-sitter，纯标准库实现；若装了 tree-sitter-languages 可走更精准的 AST 路径（未来扩展点）
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# 跳过的目录
_SKIP_DIRS = {
    ".git", ".hg", ".svn", ".venv", "venv", "__pycache__",
    "node_modules", "dist", "build", ".tangyuan", ".idea", ".vscode",
    "site-packages", ".next", ".nuxt", "target", "vendor",
}

# 支持的后缀 → 语言
_LANG_BY_EXT: Dict[str, str] = {
    ".py": "python",
    ".js": "javascript", ".jsx": "javascript",
    ".ts": "typescript", ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".swift": "swift",
    ".c": "c", ".h": "c",
    ".cpp": "cpp", ".cc": "cpp", ".hpp": "cpp",
    ".cs": "csharp",
    ".rb": "ruby",
    ".php": "php",
    ".scala": "scala",
    ".clj": "clojure",
    ".ex": "elixir", ".exs": "elixir",
    ".lua": "lua",
    ".sh": "shell", ".bash": "shell", ".zsh": "shell",
}

# 每种语言的符号正则：匹配 (name, kind)
_SYMBOL_PATTERNS: Dict[str, List[Tuple[str, str]]] = {
    "python": [
        (r"^\s*class\s+(\w+)\s*[:\(]", "class"),
        (r"^\s*def\s+(\w+)\s*\(", "def"),
        (r"^\s*async\s+def\s+(\w+)\s*\(", "def"),
        (r"^(\w+)\s*=\s*[A-Z_][A-Z0-9_]*\s*$", "const"),
    ],
    "javascript": [
        (r"^\s*class\s+(\w+)\s*[\<\{]", "class"),
        (r"^\s*export\s+default\s+function\s+(\w+)", "fn"),
        (r"^\s*export\s+function\s+(\w+)", "fn"),
        (r"^\s*function\s+(\w+)\s*\(", "fn"),
        (r"^\s*export\s+(?:async\s+)?function\s+(\w+)", "fn"),
        (r"^\s*export\s+const\s+(\w+)\s*=", "const"),
        (r"^\s*const\s+(\w+)\s*=\s*(?:async\s*)?\(", "fn"),
        (r"^\s*const\s+(\w+)\s*=\s*\([^)]*\)\s*=>", "fn"),
    ],
    "typescript": [
        (r"^\s*export\s+interface\s+(\w+)", "interface"),
        (r"^\s*interface\s+(\w+)", "interface"),
        (r"^\s*export\s+type\s+(\w+)", "type"),
        (r"^\s*type\s+(\w+)\s*=", "type"),
        (r"^\s*export\s+enum\s+(\w+)", "enum"),
        (r"^\s*enum\s+(\w+)", "enum"),
        (r"^\s*export\s+default\s+class\s+(\w+)", "class"),
        (r"^\s*export\s+class\s+(\w+)", "class"),
        (r"^\s*class\s+(\w+)", "class"),
        (r"^\s*export\s+default\s+function\s+(\w+)", "fn"),
        (r"^\s*export\s+function\s+(\w+)", "fn"),
        (r"^\s*function\s+(\w+)\s*[\(<]", "fn"),
        (r"^\s*export\s+const\s+(\w+)\s*:", "const"),
    ],
    "go": [
        (r"^func\s+(\w+)\s*\(", "func"),
        (r"^func\s+\([^)]+\)\s+(\w+)\s*\(", "method"),
        (r"^type\s+(\w+)\s+(?:struct|interface)", "type"),
        (r"^type\s+(\w+)\s+", "type"),
        (r"^var\s+(\w+)\s+", "var"),
        (r"^const\s+(\w+)\s+", "const"),
    ],
    "rust": [
        (r"^\s*pub\s+fn\s+(\w+)", "fn"),
        (r"^\s*fn\s+(\w+)", "fn"),
        (r"^\s*pub\s+struct\s+(\w+)", "struct"),
        (r"^\s*struct\s+(\w+)", "struct"),
        (r"^\s*pub\s+enum\s+(\w+)", "enum"),
        (r"^\s*enum\s+(\w+)", "enum"),
        (r"^\s*pub\s+trait\s+(\w+)", "trait"),
        (r"^\s*trait\s+(\w+)", "trait"),
        (r"^\s*pub\s+mod\s+(\w+)", "mod"),
        (r"^\s*mod\s+(\w+)", "mod"),
        (r"^\s*impl\s+(\w+)", "impl"),
    ],
    "java": [
        (r"^\s*public\s+class\s+(\w+)", "class"),
        (r"^\s*class\s+(\w+)", "class"),
        (r"^\s*public\s+interface\s+(\w+)", "interface"),
        (r"^\s*interface\s+(\w+)", "interface"),
        (r"^\s*public\s+(?:static\s+)?[\w<>,\s]+\s+(\w+)\s*\([^)]*\)\s*(?:\{|throws)", "method"),
        (r"^\s*(?:static\s+)?[\w<>,\s]+\s+(\w+)\s*\([^)]*\)\s*(?:\{|throws)", "method"),
    ],
    "c": [
        (r"^\s*(?:typedef\s+)?struct\s+(\w+)", "struct"),
        (r"^\s*(?:typedef\s+)?enum\s+(\w+)", "enum"),
        (r"^[\w\s\*]+?\s+(\w+)\s*\([^)]*\)\s*\{", "fn"),
    ],
    "cpp": [
        (r"^\s*class\s+(\w+)", "class"),
        (r"^\s*struct\s+(\w+)", "struct"),
        (r"^\s*enum\s+(?:class\s+)?(\w+)", "enum"),
        (r"^\s*namespace\s+(\w+)", "namespace"),
        (r"^[\w:<>,\s\*]+?\s+(\w+)\s*\([^)]*\)\s*(?:\{|const)", "fn"),
    ],
    "ruby": [
        (r"^\s*class\s+([\w:]+)", "class"),
        (r"^\s*module\s+([\w:]+)", "module"),
        (r"^\s*def\s+(\w+)", "def"),
        (r"^\s*def\s+self\.(\w+)", "def"),
    ],
    "php": [
        (r"^\s*class\s+(\w+)", "class"),
        (r"^\s*interface\s+(\w+)", "interface"),
        (r"^\s*function\s+(\w+)\s*\(", "fn"),
        (r"^\s*public\s+function\s+(\w+)", "fn"),
    ],
}

# 符号 kind 缩写
_KIND_ABBR = {
    "class": "C", "interface": "I", "struct": "S", "enum": "E",
    "fn": "F", "def": "F", "func": "F", "method": "M",
    "type": "T", "trait": "Tr", "impl": "Impl",
    "const": "K", "var": "V", "mod": "Mod", "namespace": "Ns",
}


@dataclass
class Symbol:
    name: str
    kind: str
    line: int


def _iter_code_files(root: Path, *, max_files: int = 500) -> List[Path]:
    out: List[Path] = []
    try:
        for p in root.rglob("*"):
            if len(out) >= max_files:
                break
            if not p.is_file():
                continue
            # 跳过任意 _SKIP_DIRS，以及 .venv* / .git* 等前缀变体（如 .venv.py39.bak）
            skipped = False
            for part in p.parts:
                if part in _SKIP_DIRS or part.startswith(".venv") or part.startswith(".git"):
                    skipped = True
                    break
            if skipped:
                continue
            ext = p.suffix.lower()
            if ext in _LANG_BY_EXT:
                out.append(p)
    except Exception:  # noqa: BLE001
        pass
    return out


def extract_symbols(path: Path, *, max_per_file: int = 50) -> List[Symbol]:
    """提取单个文件的符号。"""
    ext = path.suffix.lower()
    lang = _LANG_BY_EXT.get(ext)
    if not lang:
        return []
    patterns = _SYMBOL_PATTERNS.get(lang, [])
    if not patterns:
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    out: List[Symbol] = []
    for i, line in enumerate(text.splitlines(), 1):
        if len(out) >= max_per_file:
            break
        for pat, kind in patterns:
            try:
                m = re.match(pat, line)
            except re.error:
                continue
            if m:
                name = m.group(1)
                if name and not name.startswith("_") or kind in {"class", "interface", "struct", "enum", "trait", "type", "mod", "namespace"}:
                    out.append(Symbol(name=name, kind=kind, line=i))
                break
    return out


def build_repo_map(
    workspace: Path,
    *,
    max_files: int = 200,
    max_symbols_per_file: int = 30,
    max_total_symbols: int = 400,
    max_chars: int = 8000,
) -> str:
    """构建 workspace 的 repo map（markdown 格式，便于注入 system prompt）。"""
    files = _iter_code_files(workspace, max_files=max_files)
    if not files:
        return ""
    try:
        ws_resolved = workspace.resolve()
    except Exception:  # noqa: BLE001
        ws_resolved = workspace
    lines: List[str] = ["## Repo Map（符号级摘要）", ""]
    total = 0
    total_chars = len("\n".join(lines))
    for f in files:
        if total >= max_total_symbols:
            break
        try:
            rel = str(f.relative_to(ws_resolved))
        except ValueError:
            rel = str(f)
        syms = extract_symbols(f, max_per_file=max_symbols_per_file)
        if not syms:
            continue
        # 文件头
        file_line = f"`{rel}`"
        block = [file_line]
        for s in syms:
            abbr = _KIND_ABBR.get(s.kind, s.kind[:2])
            block.append(f"  - {abbr} {s.name}  (L{s.line})")
        new_block = "\n".join(block)
        if total_chars + len(new_block) + 1 > max_chars:
            break
        lines.append(new_block)
        total += len(syms)
        total_chars += len(new_block) + 1
    if total == 0:
        return ""
    lines.append("")
    lines.append(f"（共 {len(files)} 个代码文件，{total} 个符号）")
    return "\n".join(lines)


def cache_repo_map(workspace: Path, *, ttl_seconds: int = 600) -> str:
    """带缓存的 repo map：缓存到 .tangyuan/repomap.txt，TTL 内复用。"""
    import time
    cache_path = workspace / ".tangyuan" / "repomap.txt"
    if cache_path.exists():
        age = time.time() - cache_path.stat().st_mtime
        if age < ttl_seconds:
            try:
                return cache_path.read_text(encoding="utf-8")
            except OSError:
                pass
    text = build_repo_map(workspace)
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(text, encoding="utf-8")
    except OSError:
        pass
    return text
