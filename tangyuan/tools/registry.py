from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel

ConfirmFn = Callable[[str, str], bool]
Handler = Callable[[Dict[str, Any]], str]


class ToolSpec(BaseModel):
    name: str
    description: str
    parameters: Dict[str, Any]

    def openai_schema(self) -> Dict[str, Any]:
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
        self._specs: Dict[str, ToolSpec] = {}
        self._handlers: Dict[str, Handler] = {}

    def register(self, spec: ToolSpec, handler: Handler) -> None:
        self._specs[spec.name] = spec
        self._handlers[spec.name] = handler

    def schemas(self, names: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        if names is None:
            return [s.openai_schema() for s in self._specs.values()]
        out: List[Dict[str, Any]] = []
        for name in names:
            spec = self._specs.get(name)
            if spec:
                out.append(spec.openai_schema())
        return out

    def names(self) -> List[str]:
        return list(self._specs.keys())

    def call(self, name: str, arguments: Dict[str, Any]) -> str:
        if name not in self._handlers:
            return json.dumps({"ok": False, "error": f"未知工具: {name}"}, ensure_ascii=False)
        try:
            return self._handlers[name](arguments)
        except Exception as e:  # noqa: BLE001
            return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)
