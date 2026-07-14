from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tangyuan.tools.registry import ConfirmFn


@dataclass
class ToolContext:
    workspace: Path
    shell_timeout: int = 60
    confirm: ConfirmFn | None = None
    confirm_writes: bool = True
    confirm_shell: bool = True

    def need_confirm(self, title: str, detail: str) -> bool:
        if self.confirm is None:
            return True
        return self.confirm(title, detail)
