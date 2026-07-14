"""汤圆记忆子系统（工程化分类）。

目录约定（对齐常见 Agent memory 布局）：

全局 ~/.tangyuan/memory/
  MEMORY.md        稳定长期记忆（画像/偏好）
  YYYY-MM-DD.md    按日过程日记
  history.jsonl    对话历史事件流
  tokens.jsonl     Token 用量计量

项目 <workspace>/.tangyuan/memory/
  MEMORY.md        本仓库约定与结论
"""

from __future__ import annotations

from tangyuan.memory.history import append_history, read_history
from tangyuan.memory.paths import (
    daily_log_path,
    global_memory_dir,
    history_path,
    memory_md_path,
    project_memory_dir,
    project_memory_md_path,
    project_memory_path,
    tokens_path,
    user_memory_path,
)
from tangyuan.memory.store import (
    append_daily_log,
    append_memory,
    build_memory_prompt_section,
    ensure_default_user_memory,
    ensure_memory_files,
    estimate_messages_chars,
    read_daily_log,
    read_long_term_memory,
    read_project_notes,
    read_user_profile,
    recall_memory,
    write_memory,
)
from tangyuan.memory.tokens import (
    append_tokens,
    record_usage_from_response,
    summarize_tokens,
)

__all__ = [
    "append_daily_log",
    "append_history",
    "append_memory",
    "append_tokens",
    "build_memory_prompt_section",
    "daily_log_path",
    "ensure_default_user_memory",
    "ensure_memory_files",
    "estimate_messages_chars",
    "global_memory_dir",
    "history_path",
    "memory_md_path",
    "project_memory_dir",
    "project_memory_md_path",
    "project_memory_path",
    "read_daily_log",
    "read_history",
    "read_long_term_memory",
    "read_project_notes",
    "read_user_profile",
    "recall_memory",
    "record_usage_from_response",
    "summarize_tokens",
    "tokens_path",
    "user_memory_path",
    "write_memory",
]
