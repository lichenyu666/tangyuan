"""RAG 引擎：检索（Retrieval）→ 增强（Augment）→ 生成（Generation）。

设计要点（面试可讲）：
- 复用 SemanticIndex 做向量检索；无 API Key 时降级为纯文本检索，链路不断。
- 只依据检索到的上下文作答，找不到就明说「资料中没有」，降低幻觉。
- 每段上下文带编号与来源（文件:行号），答案可核查、可引用。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tangyuan.config import Settings
from tangyuan.tools.semantic import Hit, SemanticIndex, fallback_text_search

_SYSTEM_PROMPT = """你是一个严谨的检索增强问答助手。请严格遵守：
1. 只依据下面提供的「资料片段」回答问题，不要使用资料以外的知识。
2. 如果资料不足以回答，直接说「根据现有资料无法回答」，不要编造。
3. 回答中引用信息时，用 [编号] 标注对应的资料片段，例如 [1][2]。
4. 用简洁、准确的中文回答。"""

_DEFAULT_TOP_K = 5


@dataclass
class RetrievedChunk:
    """一段被检索到的资料。"""

    index: int
    path: str
    line: int
    score: float
    text: str

    @property
    def source(self) -> str:
        return f"{self.path}:{self.line}"


@dataclass
class RAGAnswer:
    """一次 RAG 问答的完整结果。"""

    question: str
    answer: str
    chunks: list[RetrievedChunk]
    engine: str  # "embedding" | "text"

    @property
    def sources(self) -> list[str]:
        """去重后的引用来源列表，保持出现顺序。"""
        seen: set[str] = set()
        out: list[str] = []
        for c in self.chunks:
            if c.source not in seen:
                seen.add(c.source)
                out.append(c.source)
        return out


def build_context_block(chunks: list[RetrievedChunk], *, max_chars: int = 6000) -> str:
    """把检索片段拼成带编号与出处的上下文块（供 LLM 阅读）。"""
    parts: list[str] = []
    used = 0
    for c in chunks:
        header = f"[{c.index}] 来源 {c.source}"
        body = c.text.strip()
        block = f"{header}\n{body}"
        if used + len(block) > max_chars and parts:
            break
        parts.append(block)
        used += len(block)
    return "\n\n".join(parts)


def _hits_to_chunks(hits: list[Hit]) -> list[RetrievedChunk]:
    return [
        RetrievedChunk(index=i + 1, path=h.path, line=h.line, score=h.score, text=h.snippet)
        for i, h in enumerate(hits)
    ]


class RAGEngine:
    """对一个知识库目录做检索增强问答。"""

    def __init__(
        self,
        workspace: Path,
        *,
        settings: Settings | None = None,
        client: Any = None,
        embedding_model: str = "text-embedding-3-small",
        chat_model: str | None = None,
    ) -> None:
        self.workspace = Path(workspace).resolve()
        self.settings = settings
        self.embedding_model = embedding_model
        self.chat_model = chat_model or (settings.model if settings else "deepseek-chat")

        # 生成用客户端（chat）
        self._client = client
        if self._client is None and settings is not None and settings.api_key:
            try:
                from openai import OpenAI

                self._client = OpenAI(api_key=settings.api_key, base_url=settings.base_url)
            except Exception:  # noqa: BLE001
                self._client = None

        # 检索用 embedding 客户端：优先用独立配置（很多 chat 网关如 DeepSeek 无 embedding 接口）
        embed_client = None
        if settings is not None:
            emb_key = settings.embedding_api_key or settings.api_key
            emb_base = settings.embedding_base_url or settings.base_url
            if settings.embedding_api_key and emb_key:
                try:
                    from openai import OpenAI

                    embed_client = OpenAI(api_key=emb_key, base_url=emb_base)
                except Exception:  # noqa: BLE001
                    embed_client = None
        self._index = SemanticIndex(
            self.workspace, client=embed_client, model=embedding_model
        )

    def index(self, *, force: bool = False) -> dict[str, Any]:
        """建立/更新知识库索引。"""
        return self._index.index(force=force)

    def retrieve(self, question: str, *, top_k: int = _DEFAULT_TOP_K) -> tuple[list[RetrievedChunk], str]:
        """检索：返回片段列表与使用的引擎名。"""
        engine = "embedding"
        hits: list[Hit] = []
        if self._client is not None:
            if self._index.stats().get("indexed_chunks", 0) == 0:
                self._index.index()
            hits = self._index.search(question, top_k=top_k)
        if not hits:
            engine = "text"
            hits = fallback_text_search(self.workspace, question, max_hits=top_k)
        return _hits_to_chunks(hits), engine

    def generate(self, question: str, chunks: list[RetrievedChunk]) -> str:
        """生成：让 LLM 依据检索片段作答。"""
        if not chunks:
            return "根据现有资料无法回答（没有检索到相关内容）。"
        if self._client is None:
            # 无 LLM 时只返回检索结果摘要，链路仍可用
            lines = ["未配置 LLM，仅返回检索到的相关片段："]
            for c in chunks:
                lines.append(f"[{c.index}] {c.source}\n{c.text}")
            return "\n\n".join(lines)

        context = build_context_block(chunks)
        user_prompt = f"资料片段：\n\n{context}\n\n---\n问题：{question}\n\n请依据上述资料作答，并用 [编号] 标注引用。"
        resp = self._client.chat.completions.create(
            model=self.chat_model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
        )
        return (resp.choices[0].message.content or "").strip()

    def ask(self, question: str, *, top_k: int = _DEFAULT_TOP_K) -> RAGAnswer:
        """完整 RAG：检索 → 生成 → 带引用返回。"""
        question = (question or "").strip()
        if not question:
            return RAGAnswer(question=question, answer="问题不能为空。", chunks=[], engine="text")
        chunks, engine = self.retrieve(question, top_k=top_k)
        answer = self.generate(question, chunks)
        return RAGAnswer(question=question, answer=answer, chunks=chunks, engine=engine)
