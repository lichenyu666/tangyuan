"""提示词层：Soul / System / Workspace / Compact / Distill + 全量组装。"""

from tangyuan.prompts.assemble import assemble_system_prompt
from tangyuan.prompts.system import (
    SYSTEM_PROMPT,
    build_base_system_prompt,
    load_compact_prompt,
    load_distill_prompt,
    load_soul,
    load_system_ops,
    load_workspace_prompt,
)

__all__ = [
    "SYSTEM_PROMPT",
    "assemble_system_prompt",
    "build_base_system_prompt",
    "load_compact_prompt",
    "load_distill_prompt",
    "load_soul",
    "load_system_ops",
    "load_workspace_prompt",
]
