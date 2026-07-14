"""汤圆终端视觉主题：柑橘金 + 薄荷绿 + 深墨绿，对话优先。"""

from __future__ import annotations

from rich.console import Console
from rich.theme import Theme

# 汤圆色板（终端真色）
# 柑橘金：汤底 / 薄荷绿：碗沿 / 深墨绿：背景容器
# 用户偏好：fresh green + citrus gold + deep 墨绿色；禁紫色渐变 / 通用 AI 模板
GOLD = "#F0B754"        # citrus gold（比之前更亮、更柑橘）
GOLD_DIM = "#B8924A"
MINT = "#7FE0B0"        # fresh mint（替代 JADE，更清新）
MINT_DIM = "#4FAA82"
INK = "#141A22"         # deep 墨绿调（比之前更深）
INK_SOFT = "#2A3344"
MIST = "#8B95A8"
RICE = "#F2EDE3"        # 米白正文
APRICOT = "#E8A06A"
ROSE = "#E87B7B"
STEEL = "#6E8AAB"

# 别名（兼容旧引用）
JADE = MINT

THEME = Theme(
    {
        "ty.brand": f"bold {GOLD}",
        "ty.brand.dim": GOLD_DIM,
        "ty.text": RICE,
        "ty.muted": MIST,
        "ty.accent": GOLD,
        "ty.accent.green": MINT,
        "ty.tool": STEEL,
        "ty.ok": MINT,
        "ty.warn": APRICOT,
        "ty.err": ROSE,
        "ty.rule": INK_SOFT,
        "ty.path": STEEL,
        "ty.prompt": f"bold {GOLD}",
        "ty.user": f"bold {RICE}",
        "markdown.h1": f"bold {GOLD}",
        "markdown.h2": f"bold {GOLD}",
        "markdown.h3": f"bold {STEEL}",
        "markdown.link": MINT,
        "markdown.code": f"{MINT} on {INK_SOFT}",
        "markdown.item.bullet": GOLD,
    }
)

# 极简品牌标志（去掉复杂 ASCII，参考 Claude Code）
MARK = "汤 圆"

console = Console(theme=THEME, highlight=False)
