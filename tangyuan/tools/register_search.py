"""注册 search_codebase 工具：基于 embedding 的语义检索。

无 embedding 客户端时降级为纯文本搜索。
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from tangyuan.tools.registry import ToolRegistry, ToolSpec
from tangyuan.tools.semantic import SemanticIndex, fallback_text_search


def register_search_tools(
    reg: ToolRegistry,
    workspace,
    *,
    client=None,
    embedding_model: str = "text-embedding-3-small",
) -> None:
    """注册语义检索工具。client 是 OpenAI() 实例；不传则降级为文本搜索。"""
    # 每个进程持有一个索引实例；懒初始化
    _index: Optional[SemanticIndex] = None

    def _get_index() -> SemanticIndex:
        nonlocal _index
        if _index is None:
            _index = SemanticIndex(workspace, client=client, model=embedding_model)
        return _index

    def search_handler(args: Dict[str, Any]) -> str:
        query = (args.get("query") or "").strip()
        if not query:
            return json.dumps({"ok": False, "error": "query 不能为空"}, ensure_ascii=False)
        top_k = int(args.get("top_k") or 8)
        reindex = bool(args.get("reindex", False))
        try:
            idx = _get_index()
            # 首次或 reindex 时建索引
            if reindex:
                stats = idx.index(force=True)
            else:
                # 先看有没有索引
                s = idx.stats()
                if s["indexed_chunks"] == 0:
                    stats = idx.index()
                else:
                    stats = None
            hits = idx.search(query, top_k=top_k)
            if not hits and client is None:
                # 降级文本搜索
                hits = fallback_text_search(workspace, query, max_hits=top_k)
            return json.dumps(
                {
                    "ok": True,
                    "engine": "embedding" if client is not None else "text",
                    "hits": [
                        {
                            "path": h.path,
                            "line": h.line,
                            "score": round(h.score, 4),
                            "snippet": h.snippet,
                        }
                        for h in hits
                    ],
                    "stats": stats,
                },
                ensure_ascii=False,
            )
        except Exception as e:  # noqa: BLE001
            # 任何异常都降级到文本搜索
            try:
                hits = fallback_text_search(workspace, query, max_hits=top_k)
                return json.dumps(
                    {
                        "ok": True,
                        "engine": "text_fallback",
                        "hits": [
                            {
                                "path": h.path,
                                "line": h.line,
                                "score": round(h.score, 4),
                                "snippet": h.snippet,
                            }
                            for h in hits
                        ],
                        "fallback_reason": str(e),
                    },
                    ensure_ascii=False,
                )
            except Exception as e2:  # noqa: BLE001
                return json.dumps(
                    {"ok": False, "error": f"语义检索失败：{e}; 文本兜底也失败：{e2}"},
                    ensure_ascii=False,
                )

    reg.register(
        ToolSpec(
            name="search_codebase",
            description=(
                "语义代码检索（基于 embedding）：用自然语言问「这个项目在哪里处理 X」之类的问题。"
                "返回最相似的代码块路径与片段。比 search_text 更适合「找概念」而非「找字面字符串」。"
                "可选 reindex=true 强制重建索引；默认按文件 mtime 增量更新。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "自然语言查询，如「where is auth handled」",
                    },
                    "top_k": {"type": "integer", "default": 8},
                    "reindex": {"type": "boolean", "default": False},
                },
                "required": ["query"],
            },
        ),
        search_handler,
    )

    def index_stats_handler(args: Dict[str, Any]) -> str:
        try:
            idx = _get_index()
            return json.dumps({"ok": True, "stats": idx.stats()}, ensure_ascii=False)
        except Exception as e:  # noqa: BLE001
            return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)

    reg.register(
        ToolSpec(
            name="search_codebase_stats",
            description="查看语义检索索引的统计信息（已索引文件数、块数、db 路径）。",
            parameters={"type": "object", "properties": {}},
        ),
        index_stats_handler,
    )
