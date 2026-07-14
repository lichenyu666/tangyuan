"""汤圆 RAG（检索增强生成）子系统。

复用 tools/semantic.py 的 SemanticIndex 做检索，补齐「增强 + 生成」两步：
把检索到的片段拼进提示词，让 LLM 只依据这些内容作答，并给出可核查的引用出处。
"""

from __future__ import annotations

from tangyuan.rag.engine import RAGAnswer, RAGEngine, RetrievedChunk, build_context_block

__all__ = ["RAGAnswer", "RAGEngine", "RetrievedChunk", "build_context_block"]
