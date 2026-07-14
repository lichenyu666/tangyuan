from __future__ import annotations

from tangyuan.tools.context import ToolContext
from tangyuan.tools.office import create_pptx
from tangyuan.tools.registry import ToolSpec
from tangyuan.tools.web import fetch_url, web_search


def register_web_tools(reg, ctx: ToolContext) -> None:
    reg.register(
        ToolSpec(
            name="web_search",
            description="搜索网页，返回标题/链接/摘要。需要查资料、新闻、文档时使用。",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
        ),
        lambda args: web_search(args["query"], int(args.get("max_results") or 5)),
    )

    reg.register(
        ToolSpec(
            name="fetch_url",
            description="抓取网页文本内容（简单提取，适合文档页）。",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "max_chars": {"type": "integer", "default": 8000},
                },
                "required": ["url"],
            },
        ),
        lambda args: fetch_url(args["url"], int(args.get("max_chars") or 8000)),
    )


def register_office_tools(reg, ctx: ToolContext) -> None:
    workspace = ctx.workspace
    reg.register(
        ToolSpec(
            name="create_pptx",
            description="生成简单 PPTX。slides 为字符串数组，每项一页标题+正文可用换行分隔。",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "输出路径，如 output/demo.pptx"},
                    "title": {"type": "string"},
                    "slides": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "每页内容：第一行当标题，其余当正文",
                    },
                },
                "required": ["path", "slides"],
            },
        ),
        lambda args: create_pptx(
            workspace,
            args["path"],
            args.get("title") or "汤圆生成",
            list(args.get("slides") or []),
        ),
    )
