"""汤圆公开 Web Demo（Gradio）。

本地：
  pip install -e '.[web]'
  python -m tangyuan.web.app

Hugging Face Spaces：见仓库根 Dockerfile（端口 7860）。
"""

from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Deque, Dict, List, Optional, Tuple

from tangyuan.agent import TangyuanAgent
from tangyuan.config import load_settings
from tangyuan.trace import TraceLogger
from tangyuan.web.demo_tools import build_demo_tools

# 限流与会话上限（防滥用 / 控费用）
_MAX_MESSAGES_PER_SESSION = 12
_MAX_REQUESTS_PER_MINUTE = 8
_MAX_STEPS = 12
_SESSION_TTL_SEC = 45 * 60

_repo_root = Path(__file__).resolve().parent.parent.parent
_DEFAULT_WORKSPACE = _repo_root / "demo_workspace"

_sessions: Dict[str, Tuple[TangyuanAgent, float]] = {}
_session_msg_count: Dict[str, int] = defaultdict(int)
_rate_buckets: Dict[str, Deque[float]] = defaultdict(deque)
_lock = threading.Lock()


def _resolve_workspace() -> Path:
    env = os.environ.get("TANGYUAN_DEMO_WORKSPACE", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    if _DEFAULT_WORKSPACE.is_dir():
        return _DEFAULT_WORKSPACE.resolve()
    return _repo_root.resolve()


def _rate_ok(key: str) -> bool:
    now = time.time()
    bucket = _rate_buckets[key]
    while bucket and now - bucket[0] > 60:
        bucket.popleft()
    if len(bucket) >= _MAX_REQUESTS_PER_MINUTE:
        return False
    bucket.append(now)
    return True


def _get_or_create_agent(session_id: str) -> TangyuanAgent:
    now = time.time()
    with _lock:
        stale = [k for k, (_, ts) in _sessions.items() if now - ts > _SESSION_TTL_SEC]
        for k in stale:
            _sessions.pop(k, None)
            _session_msg_count.pop(k, None)

        existing = _sessions.get(session_id)
        if existing is not None:
            agent, _ = existing
            _sessions[session_id] = (agent, now)
            return agent

        ws = _resolve_workspace()
        settings = load_settings(workspace=str(ws), max_steps=_MAX_STEPS)
        if not settings.api_key:
            raise RuntimeError(
                "未配置 TANGYUAN_API_KEY。本地请复制 .env.example 为 .env；"
                "Hugging Face Spaces 请在 Secrets 中设置。"
            )
        tools = build_demo_tools(ws, settings=settings)
        agent = TangyuanAgent(
            settings,
            tools,
            TraceLogger(ws),
            on_event=lambda *_a, **_k: None,
            forced_skill_id="explain-repo",
        )
        _sessions[session_id] = (agent, now)
        return agent


def _format_tool_line(name: str, preview: str) -> str:
    preview = (preview or "").replace("\n", " ").strip()
    if len(preview) > 120:
        preview = preview[:117] + "..."
    return f"`{name}` → {preview}" if preview else f"`{name}`"


def chat(message: str, history: List, request=None) -> str:
    """Gradio ChatInterface 回调。"""
    text = (message or "").strip()
    if not text:
        return "请输入问题，例如：汤圆是什么？架构怎么分层？"
    if len(text) > 2000:
        return "单条消息过长（上限 2000 字），请缩短后再试。"

    session_id = "anon"
    if request is not None:
        try:
            session_id = getattr(request, "session_hash", None) or request.client.host or "anon"
        except Exception:  # noqa: BLE001
            session_id = "anon"

    if not _rate_ok(session_id):
        return "请求太频繁，请稍后再试（每分钟最多 8 次）。"

    if _session_msg_count[session_id] >= _MAX_MESSAGES_PER_SESSION:
        return (
            f"本会话已达 {_MAX_MESSAGES_PER_SESSION} 条上限。"
            "刷新页面可开新会话；完整能力请本地安装：https://github.com/lichenyu666/tangyuan"
        )

    tool_lines: List[str] = []
    answer_parts: List[str] = []

    def on_event(kind: str, **payload) -> None:
        if kind == "tool_call":
            name = payload.get("name") or "?"
            args = payload.get("args") or {}
            preview = str(args)[:120]
            tool_lines.append(f"- 调用 {_format_tool_line(name, preview)}")
        elif kind == "tool_result":
            if tool_lines:
                tool_lines[-1] += " ✓"
        elif kind == "stream_delta":
            answer_parts.append(payload.get("delta") or "")
        elif kind == "final":
            # 流式已收集；若无流式则用 final
            if not answer_parts:
                answer_parts.append(payload.get("content") or "")

    try:
        agent = _get_or_create_agent(session_id)
        agent.on_event = on_event
        final = agent.ask(text)
        _session_msg_count[session_id] += 1
    except Exception as e:  # noqa: BLE001
        return f"出错了：{e}"

    body = "".join(answer_parts).strip() or (final or "").strip() or "（无回复）"
    if tool_lines:
        tools_block = "\n".join(tool_lines[:12])
        return f"{body}\n\n---\n**本次工具**\n{tools_block}"
    return body


def build_app():
    import gradio as gr

    examples = [
        "汤圆是什么？一句话介绍一下",
        "这个仓库的目录结构是怎样的？",
        "本地怎么安装并启动？",
        "在线 Demo 和完整终端版有什么区别？",
    ]

    demo = gr.ChatInterface(
        fn=chat,
        title="汤圆 Tangyuan · Demo",
        description=(
            "李晨雨独立实现的终端 Agent 公开演示。"
            "本 Demo **只读**：可讲解仓库、搜网页；不能执行 shell / 改文件。"
            "完整版请看 "
            "[GitHub](https://github.com/lichenyu666/tangyuan)。"
        ),
        examples=examples,
        cache_examples=False,
        concurrency_limit=4,
    )
    return demo


def main() -> None:
    demo = build_app()
    share = os.environ.get("GRADIO_SHARE", "").strip().lower() in {"1", "true", "yes"}
    demo.queue(default_concurrency_limit=4).launch(
        server_name=os.environ.get("GRADIO_SERVER_NAME", "0.0.0.0"),
        server_port=int(os.environ.get("GRADIO_SERVER_PORT", "7860")),
        share=share,
    )


if __name__ == "__main__":
    main()
