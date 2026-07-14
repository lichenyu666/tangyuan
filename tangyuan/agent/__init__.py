"""汤圆 Agent 包。"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tangyuan.agent.core import TangyuanAgent

__all__ = ["TangyuanAgent"]


def __getattr__(name: str):
    if name == "TangyuanAgent":
        from tangyuan.agent.core import TangyuanAgent as _TangyuanAgent

        return _TangyuanAgent
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
