"""语义代码检索：基于 embedding 的语义索引与查询。

设计：
- 把 workspace 下代码文件分块（按符号/函数边界），调 embedding API 生成向量。
- 向量存到 workspace 本地 sqlite（<workspace>/.tangyuan/semantic.db）。
- 查询时把 query 也 embedding，与库内向量做余弦相似度，返回 top-K。
- 索引按文件 mtime 增量更新（只重新 embedding 改动的文件）。
- 失败优雅降级：API 不通时退到纯 ripgrep 文本搜索。

依赖：sqlite3（标准库），OpenAI embeddings API（复用 agent 同一份 key/base_url）。
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# 支持的代码后缀（按重要性排序）
_CODE_EXTS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".kt",
    ".swift", ".c", ".h", ".cpp", ".hpp", ".cc", ".cs", ".rb", ".php",
    ".scala", ".ml", ".hs", ".clj", ".ex", ".exs", ".vim", ".lua",
    ".sh", ".bash", ".zsh", ".fish",
    ".md", ".rst", ".txt",  # 文档也算"代码内容"
    ".yml", ".yaml", ".toml", ".ini", ".cfg", ".conf",
    ".sql",
}

# 跳过的目录
_SKIP_DIRS = {
    ".git", ".hg", ".svn",
    ".venv", "venv", "__pycache__", "node_modules", "dist", "build",
    ".tangyuan", ".idea", ".vscode",
    "site-packages",
}

# 每块最大字符（embedding 模型有 token 限制，留余量）
_CHUNK_MAX = 1500
_CHUNK_OVERLAP = 200


@dataclass
class Hit:
    path: str
    line: int
    score: float
    snippet: str


def _is_code_file(path: Path) -> bool:
    if path.suffix.lower() not in _CODE_EXTS:
        return False
    # 跳过隐藏文件
    if any(part.startswith(".") and part not in {".env"} for part in path.parts[:-1]):
        return False
    return True


def _iter_code_files(root: Path, *, max_files: int = 1000) -> list[Path]:
    out: list[Path] = []
    try:
        for p in root.rglob("*"):
            if len(out) >= max_files:
                break
            if not p.is_file():
                continue
            if any(part in _SKIP_DIRS for part in p.parts):
                continue
            if _is_code_file(p):
                out.append(p)
    except Exception:  # noqa: BLE001
        pass
    return out


def _chunk_text(text: str, *, max_chars: int = _CHUNK_MAX, overlap: int = _CHUNK_OVERLAP) -> list[tuple[int, str]]:
    """把文本按行分块，每块 max_chars 字符，相邻块有 overlap 重叠。"""
    lines = text.splitlines()
    if not lines:
        return []
    chunks: list[tuple[int, str]] = []
    cur: list[str] = []
    cur_len = 0
    start_line = 1
    line_no = 0
    for line in lines:
        line_no += 1
        cur.append(line)
        cur_len += len(line) + 1
        if cur_len >= max_chars:
            block = "\n".join(cur)
            chunks.append((start_line, block))
            # 保留末尾 overlap 行
            keep_lines: list[str] = []
            keep_len = 0
            for x in reversed(cur):
                if keep_len + len(x) > overlap:
                    break
                keep_lines.insert(0, x)
                keep_len += len(x) + 1
            cur = keep_lines
            cur_len = sum(len(x) + 1 for x in cur)
            start_line = line_no - len(cur) + 1
    if cur:
        chunks.append((start_line, "\n".join(cur)))
    return chunks


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class SemanticIndex:
    """workspace 本地语义索引（sqlite + embedding API）。"""

    def __init__(self, workspace: Path, *, client=None, model: str = "text-embedding-3-small") -> None:
        self.workspace = workspace.resolve()
        self.db_path = self.workspace / ".tangyuan" / "semantic.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.client = client
        self.model = model
        self._conn: sqlite3.Connection | None = None

    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chunks (
                    path TEXT NOT NULL,
                    line INTEGER NOT NULL,
                    mtime REAL NOT NULL,
                    text TEXT NOT NULL,
                    embedding TEXT,
                    PRIMARY KEY (path, line)
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_chunks_path ON chunks(path)"
            )
            self._conn.commit()
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _embed(self, texts: list[str]) -> list[list[float]]:
        if not texts or self.client is None:
            return []
        # 批量请求，单批最多 64 条
        out: list[list[float]] = []
        for i in range(0, len(texts), 64):
            batch = texts[i:i + 64]
            try:
                resp = self.client.embeddings.create(model=self.model, input=batch)
                out.extend([d.embedding for d in resp.data])
            except Exception:  # noqa: BLE001
                # 失败的批次填空向量，保证索引对齐
                out.extend([[] for _ in batch])
        return out

    def index(self, *, force: bool = False, max_files: int = 1000) -> dict[str, Any]:
        """索引 workspace 代码文件。返回统计信息。"""
        conn = self._connect()
        files = _iter_code_files(self.workspace, max_files=max_files)
        added = 0
        skipped = 0
        errors = 0
        for f in files:
            try:
                mtime = f.stat().st_mtime
                # 检查是否已索引且最新
                if not force:
                    cur = conn.execute(
                        "SELECT mtime FROM chunks WHERE path=? LIMIT 1",
                        (str(f.relative_to(self.workspace)),),
                    ).fetchone()
                    if cur and cur[0] >= mtime:
                        skipped += 1
                        continue
                text = f.read_text(encoding="utf-8", errors="replace")
                if not text.strip():
                    continue
                rel = str(f.relative_to(self.workspace))
                # 删除旧块
                conn.execute("DELETE FROM chunks WHERE path=?", (rel,))
                chunks = _chunk_text(text)
                # 批量 embedding
                chunk_texts = [c[1] for c in chunks]
                embeddings = self._embed(chunk_texts) if self.client else []
                for (line, block), emb in zip(chunks, embeddings or [None] * len(chunks), strict=False):
                    conn.execute(
                        "INSERT INTO chunks (path, line, mtime, text, embedding) VALUES (?, ?, ?, ?, ?)",
                        (rel, line, mtime, block, json.dumps(emb) if emb else None),
                    )
                added += 1
            except Exception:  # noqa: BLE001
                errors += 1
                continue
        conn.commit()
        return {"added": added, "skipped": skipped, "errors": errors, "total_files": len(files)}

    def search(self, query: str, *, top_k: int = 8) -> list[Hit]:
        """语义检索：返回 top_k 最相似块。"""
        if self.client is None:
            return []
        conn = self._connect()
        q_emb = self._embed([query])
        if not q_emb or not q_emb[0]:
            return []
        q_vec = q_emb[0]
        # 拉所有有 embedding 的块，做余弦相似度
        rows = conn.execute(
            "SELECT path, line, text, embedding FROM chunks WHERE embedding IS NOT NULL"
        ).fetchall()
        scored: list[tuple[float, str, int, str]] = []
        for path, line, text, emb_json in rows:
            try:
                emb = json.loads(emb_json)
            except json.JSONDecodeError:
                continue
            score = _cosine(q_vec, emb)
            scored.append((score, path, line, text))
        scored.sort(key=lambda x: -x[0])
        out: list[Hit] = []
        for score, path, line, text in scored[:top_k]:
            snippet = text[:400].replace("\n", " | ")
            out.append(Hit(path=path, line=line, score=score, snippet=snippet))
        return out

    def stats(self) -> dict[str, Any]:
        conn = self._connect()
        total = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        with_emb = conn.execute(
            "SELECT COUNT(*) FROM chunks WHERE embedding IS NOT NULL"
        ).fetchone()[0]
        files = conn.execute("SELECT COUNT(DISTINCT path) FROM chunks").fetchone()[0]
        return {
            "total_chunks": total,
            "indexed_chunks": with_emb,
            "files": files,
            "db_path": str(self.db_path),
        }


def _tokenize_query(query: str) -> list[str]:
    """把查询切成检索词：英文/数字按空白与词边界；中文用连续汉字的二元组（bigram）。

    这样即使没有 embedding，中文连写查询（如「记忆系统分层」）也能有效检索，
    而不是把整句当成一个字面串去匹配。
    """
    q = query.strip().lower()
    if not q:
        return []
    tokens: list[str] = []
    # 英文/数字词
    tokens.extend(re.findall(r"[a-z0-9_]+", q))
    # 连续中文串 → 二元组；单字中文串保留单字
    for run in re.findall(r"[\u4e00-\u9fff]+", q):
        if len(run) == 1:
            tokens.append(run)
        else:
            tokens.extend(run[i : i + 2] for i in range(len(run) - 1))
    # 去重保序
    seen: set[str] = set()
    out: list[str] = []
    for t in tokens:
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def fallback_text_search(workspace: Path, query: str, *, max_hits: int = 8) -> list[Hit]:
    """embedding 不可用时的纯文本兜底（支持中文二元分词）。"""
    tokens = _tokenize_query(query)
    if not tokens:
        return []
    files = _iter_code_files(workspace, max_files=500)
    scored: list[tuple[float, str, int, str]] = []
    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = str(f.relative_to(workspace))
        lower = text.lower()
        # 评分：各词命中次数（截断上限）之和 / 词数，命中不同词越多分越高
        hits_per_token = [lower.count(t) for t in tokens]
        matched = sum(1 for h in hits_per_token if h > 0)
        if matched == 0:
            continue
        freq_score = sum(min(h, 5) for h in hits_per_token) / max(len(tokens), 1)
        # 覆盖率加权：命中的不同词占比
        coverage = matched / len(tokens)
        score = freq_score * (0.5 + coverage)
        # 找首个命中行
        first_line = 1
        for i, line in enumerate(text.splitlines(), 1):
            ll = line.lower()
            if any(t in ll for t in tokens):
                first_line = i
                break
        snippet = text[:400].replace("\n", " | ")
        scored.append((score, rel, first_line, snippet))
    scored.sort(key=lambda x: -x[0])
    return [Hit(path=p, line=ln, score=s, snippet=sn) for s, p, ln, sn in scored[:max_hits]]
