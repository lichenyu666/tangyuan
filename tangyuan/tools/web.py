from __future__ import annotations

import json
import re


def web_search(query: str, max_results: int) -> str:
    try:
        from ddgs import DDGS
    except ImportError:
        return json.dumps({"ok": False, "error": "缺少 ddgs 依赖，请 pip install ddgs"}, ensure_ascii=False)
    rows = []
    with DDGS() as ddgs:
        for item in ddgs.text(query, max_results=max_results):
            rows.append(
                {
                    "title": item.get("title"),
                    "url": item.get("href"),
                    "snippet": item.get("body"),
                }
            )
    return json.dumps({"ok": True, "query": query, "results": rows}, ensure_ascii=False)


def fetch_url(url: str, max_chars: int) -> str:
    import httpx

    headers = {"User-Agent": "TangyuanAgent/0.2"}
    with httpx.Client(follow_redirects=True, timeout=30.0, headers=headers) as client:
        r = client.get(url)
        r.raise_for_status()
        text = r.text
    # 极简去标签
    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", text)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return json.dumps(
        {"ok": True, "url": url, "content": text[:max_chars]},
        ensure_ascii=False,
    )

