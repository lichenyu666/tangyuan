"""Hooks：生命周期扩展点（对齐 Claude Code / 教学 step12 精简版）。"""

from __future__ import annotations

from typing import Any


class HookDecision:
    """allow | deny | ask | block"""

    def __init__(
        self,
        action: str,
        reason: str = "",
        updated_input: dict[str, Any] | None = None,
    ):
        self.action = action
        self.reason = reason
        self.updated_input = updated_input

    @property
    def is_blocking(self) -> bool:
        return self.action in ("deny", "block")

    def to_message(self) -> str:
        label = {
            "deny": "拒绝",
            "block": "阻止",
            "ask": "需要确认",
            "allow": "已放行",
        }.get(self.action, self.action)
        msg = f"[Hook: {label}] {self.reason}"
        if self.updated_input:
            msg += f"（参数已改写：{list(self.updated_input.keys())}）"
        return msg


class Hook:
    name: str = ""
    matcher: str = "*"

    def matches(self, tool_name: str | None) -> bool:
        if not tool_name or self.matcher in ("*", ""):
            return True
        patterns = [p.strip() for p in self.matcher.replace(",", "|").split("|")]
        return tool_name in patterns

    def before_tool_call(self, ctx: dict[str, Any]) -> Any:
        return None

    def after_tool_call(self, ctx: dict[str, Any]) -> Any:
        return None

    def on_stop(self, ctx: dict[str, Any]) -> Any:
        return None


class HookRegistry:
    def __init__(self) -> None:
        self._hooks: list[Hook] = []

    def register(self, hook: Hook) -> None:
        self._hooks.append(hook)

    def emit(
        self,
        event: str,
        ctx: dict[str, Any],
        *,
        tool_matcher: str | None = None,
    ) -> Any:
        for hook in self._hooks:
            if event in ("before_tool_call", "after_tool_call"):
                if not hook.matches(tool_matcher):
                    continue
            handler = getattr(hook, event, None)
            if not callable(handler):
                continue
            try:
                result = handler(ctx)
            except Exception as e:  # noqa: BLE001
                ctx.setdefault("_hook_errors", []).append(f"{hook.name}: {e}")
                continue
            if result is None:
                continue
            if isinstance(result, HookDecision) and result.action == "allow":
                if result.updated_input is not None:
                    ctx["input"] = result.updated_input
                continue
            return result
        return None


def build_default_hooks(*, audit_path: Any | None = None) -> HookRegistry:
    from tangyuan.hooks.builtin import (
        OutputTruncateHook,
        PlanStopGateHook,
        ToolAuditHook,
    )

    reg = HookRegistry()
    reg.register(OutputTruncateHook(max_chars=12000))
    reg.register(ToolAuditHook(path=audit_path))
    reg.register(PlanStopGateHook())
    return reg
