from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _env_file_candidates() -> Tuple[Path, ...]:
    """按优先级查找 .env：当前目录 → ~/.tangyuan → 仓库根目录。"""
    return (
        Path.cwd() / ".env",
        Path.home() / ".tangyuan" / ".env",
        Path(__file__).resolve().parent.parent / ".env",
    )


def resolve_env_files() -> Tuple[str, ...]:
    return tuple(str(p) for p in _env_file_candidates() if p.is_file())


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=resolve_env_files() or None,
        env_file_encoding="utf-8",
        env_prefix="TANGYUAN_",
        extra="ignore",
    )

    api_key: str = Field(default="", description="LLM API Key")
    base_url: str = Field(
        default="https://api.deepseek.com",
        description="OpenAI 兼容 Base URL",
    )
    model: str = Field(default="deepseek-chat")
    embedding_model: str = Field(
        default="text-embedding-3-small",
        description="语义检索用的 embedding 模型名",
    )
    max_steps: int = Field(default=30, ge=1, le=100)
    workspace: Path = Field(default=Path("."))
    temperature: float = Field(default=0.2, ge=0, le=2)
    shell_timeout: int = Field(default=60, ge=1, le=600)
    require_confirm_shell: bool = Field(
        default=True,
        description="执行 shell 前是否需要确认（-y 时关闭）",
    )
    confirm_writes: bool = Field(
        default=True,
        description="写入/打补丁前是否需要确认（-y 时关闭）",
    )
    # 会话压缩：非 system 消息条数或字符数超阈值时压缩
    compact_after_messages: int = Field(default=24, ge=8, le=200)
    compact_keep_recent: int = Field(default=10, ge=4, le=80)
    compact_after_chars: int = Field(default=80000, ge=10000, le=500000)

    def resolve_workspace(self) -> Path:
        return self.workspace.expanduser().resolve()


def load_settings(
    workspace: Optional[str] = None,
    model: Optional[str] = None,
    max_steps: Optional[int] = None,
) -> Settings:
    s = Settings()
    if workspace:
        s.workspace = Path(workspace)
    if model:
        s.model = model
    if max_steps is not None:
        s.max_steps = max_steps
    return s
