from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from tangyuan.tools.registry import ConfirmFn


@dataclass
class ToolContext:
    workspace: Path
    shell_timeout: int = 60
    confirm: Optional[ConfirmFn] = None
    confirm_writes: bool = True
    confirm_shell: bool = True

    def need_confirm(self, title: str, detail: str) -> bool:
        if self.confirm is None:
            return True
        return self.confirm(title, detail)
