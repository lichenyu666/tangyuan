from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

ConfirmFn = Callable[[str, str], bool]
Handler = Callable[[dict[str, Any]], str]


class ToolSpec(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any]

    def openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}
        self._handlers: dict[str, Handler] = {}

    def register(self, spec: ToolSpec, handler: Handler) -> None:
        self._specs[spec.name] = spec
        self._handlers[spec.name] = handler

    def unregister(self, name: str) -> None:
        self._specs.pop(name, None)
        self._handlers.pop(name, None)

    def schemas(self, names: list[str] | None = None) -> list[dict[str, Any]]:
        if names is None:
            return [s.openai_schema() for s in self._specs.values()]
        out: list[dict[str, Any]] = []
        for name in names:
            spec = self._specs.get(name)
            if spec:
                out.append(spec.openai_schema())
        return out

    def names(self) -> list[str]:
        return list(self._specs.keys())

    def call(self, name: str, arguments: dict[str, Any]) -> str:
        if name not in self._handlers:
            return json.dumps({"ok": False, "error": f"未知工具: {name}"}, ensure_ascii=False)
        try:
            return self._handlers[name](arguments)
        except Exception as e:  # noqa: BLE001
            return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)
