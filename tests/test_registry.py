"""ToolRegistry 的纯逻辑单测（无需 API Key）。"""

from __future__ import annotations

import json

from tangyuan.tools.registry import ToolRegistry, ToolSpec


def _spec(name: str) -> ToolSpec:
    return ToolSpec(
        name=name,
        description=f"test tool {name}",
        parameters={"type": "object", "properties": {}},
    )


def test_register_and_call() -> None:
    reg = ToolRegistry()
    reg.register(_spec("echo"), lambda args: json.dumps({"ok": True, "echo": args}))
    assert "echo" in reg.names()

    out = json.loads(reg.call("echo", {"x": 1}))
    assert out["ok"] is True
    assert out["echo"] == {"x": 1}


def test_unregister() -> None:
    reg = ToolRegistry()
    reg.register(_spec("gone"), lambda args: "1")
    assert "gone" in reg.names()
    reg.unregister("gone")
    assert "gone" not in reg.names()
    # 卸载不存在的名字应安全无异常
    reg.unregister("nonexistent")


def test_unknown_tool_returns_error() -> None:
    reg = ToolRegistry()
    out = json.loads(reg.call("missing", {}))
    assert out["ok"] is False
    assert "未知工具" in out["error"]


def test_handler_exception_is_wrapped() -> None:
    reg = ToolRegistry()

    def boom(_args: dict) -> str:
        raise ValueError("boom")

    reg.register(_spec("boom"), boom)
    out = json.loads(reg.call("boom", {}))
    assert out["ok"] is False
    assert "boom" in out["error"]


def test_openai_schema_shape() -> None:
    spec = _spec("t")
    schema = spec.openai_schema()
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "t"
    assert "parameters" in schema["function"]
