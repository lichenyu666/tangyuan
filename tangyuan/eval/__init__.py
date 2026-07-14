"""汤圆评测集：端到端任务用例 + 自动判定。

设计：
- 每个 EvalCase 在隔离临时 workspace 中跑（避免污染真实仓库）。
- 断言分两类：对最终回复（reply_*）、对文件系统/命令（file_* / shell_*）。
- 不依赖外网的用例占大多数；少数 web 类用例标记为 network=True 可选跳过。
"""

from __future__ import annotations

from .runner import EvalCase, EvalResult, run_eval, run_single
from .cases import DEFAULT_CASES

__all__ = [
    "DEFAULT_CASES",
    "EvalCase",
    "EvalResult",
    "run_eval",
    "run_single",
]
