"""RAG 引擎离线单测（不调用任何 LLM / embedding API）。"""

from __future__ import annotations

from pathlib import Path

from tangyuan.rag import RAGAnswer, RAGEngine, RetrievedChunk, build_context_block

_DEMO = Path(__file__).resolve().parent.parent / "examples" / "rag_demo"


def _chunk(i: int, path: str, line: int, text: str) -> RetrievedChunk:
    return RetrievedChunk(index=i, path=path, line=line, score=1.0, text=text)


def test_chunk_source_format() -> None:
    c = _chunk(1, "a/b.md", 12, "hello")
    assert c.source == "a/b.md:12"


def test_build_context_block_has_index_and_source() -> None:
    chunks = [_chunk(1, "x.md", 1, "AAA"), _chunk(2, "y.md", 5, "BBB")]
    block = build_context_block(chunks)
    assert "[1] 来源 x.md:1" in block
    assert "[2] 来源 y.md:5" in block
    assert "AAA" in block and "BBB" in block


def test_build_context_block_respects_max_chars() -> None:
    chunks = [_chunk(i, f"f{i}.md", 1, "x" * 100) for i in range(1, 11)]
    block = build_context_block(chunks, max_chars=250)
    # 至少保留第一段，且不会把 10 段全塞进去
    assert "[1]" in block
    assert "[10]" not in block


def test_answer_sources_are_deduped_in_order() -> None:
    ans = RAGAnswer(
        question="q",
        answer="a",
        chunks=[
            _chunk(1, "a.md", 1, "x"),
            _chunk(2, "a.md", 1, "y"),  # 同一来源
            _chunk(3, "b.md", 3, "z"),
        ],
        engine="text",
    )
    assert ans.sources == ["a.md:1", "b.md:3"]


def test_generate_without_chunks_declines() -> None:
    engine = RAGEngine(_DEMO, settings=None)
    out = engine.generate("任意问题", [])
    assert "无法回答" in out


def test_empty_question_returns_gracefully() -> None:
    engine = RAGEngine(_DEMO, settings=None)
    ans = engine.ask("   ")
    assert ans.chunks == []
    assert "不能为空" in ans.answer


def test_retrieve_text_fallback_finds_demo_docs() -> None:
    # 无 client → 走文本兜底检索，应能在示例知识库里命中 RAG 相关内容
    engine = RAGEngine(_DEMO, settings=None)
    chunks, eng = engine.retrieve("什么是 RAG 检索增强生成", top_k=3)
    assert eng == "text"
    assert len(chunks) >= 1
    assert any("rag" in c.path.lower() or "RAG" in c.text or "检索" in c.text for c in chunks)


def test_ask_without_llm_returns_retrieved_snippets() -> None:
    # 注：无 API 的文本兜底按空格分词，故查询用带空格的关键词（embedding 模式无此限制）
    engine = RAGEngine(_DEMO, settings=None)
    ans = engine.ask("记忆 分层", top_k=3)
    # 无 LLM 时应降级为返回检索片段，而不是报错
    assert ans.chunks
    assert "未配置 LLM" in ans.answer
