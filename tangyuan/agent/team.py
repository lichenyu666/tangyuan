"""Agent Team：持久队友 + 文件 inbox（产品版，对齐教学 step10 能力）。"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from openai import OpenAI

from tangyuan.config import Settings
from tangyuan.memory import record_usage_from_response
from tangyuan.tools.registry import ToolRegistry

VALID_MSG_TYPES = frozenset(
    {
        "message",
        "broadcast",
        "shutdown_request",
        "shutdown_response",
        "plan_approval_response",
    }
)
RUNTIME_STATUSES = frozenset({"idle", "working"})

# 队友可用工具（不含规划/派遣/组队，避免递归乱套）
_TEAMMATE_TOOLS = [
    "list_dir",
    "read_file",
    "write_file",
    "apply_patch",
    "search_text",
    "run_shell",
    "web_search",
    "fetch_url",
    "load_skill",
    "open_path",
]


class MessageBus:
    """每个成员一个 JSONL inbox：发送=追加，读取=drain 清空。"""

    def __init__(self, inbox_dir: Path):
        self.dir = inbox_dir
        self.dir.mkdir(parents=True, exist_ok=True)

    def send(
        self,
        sender: str,
        to: str,
        content: str,
        msg_type: str = "message",
        extra: Optional[Dict[str, Any]] = None,
    ) -> str:
        if msg_type not in VALID_MSG_TYPES:
            return f"Error: invalid msg_type '{msg_type}'，允许: {sorted(VALID_MSG_TYPES)}"
        msg: Dict[str, Any] = {
            "type": msg_type,
            "from": sender,
            "content": content,
            "timestamp": time.time(),
        }
        if extra:
            msg.update(extra)
        path = self.dir / f"{to}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(msg, ensure_ascii=False) + "\n")
        return f"已送达 {to} 的 inbox：{msg_type}"

    def read_inbox(self, name: str) -> List[Dict[str, Any]]:
        path = self.dir / f"{name}.jsonl"
        if not path.exists():
            return []
        messages: List[Dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                messages.append(json.loads(line))
            except json.JSONDecodeError as e:
                messages.append(
                    {
                        "type": "message",
                        "from": "system",
                        "content": f"inbox 行解析失败: {e}",
                        "timestamp": time.time(),
                    }
                )
        path.write_text("", encoding="utf-8")
        return messages

    def broadcast(self, sender: str, content: str, teammates: List[str]) -> str:
        count = 0
        for name in teammates:
            if name == sender:
                continue
            self.send(sender, name, content, "broadcast")
            count += 1
        return f"已广播给 {count} 位队友"


class TeammateManager:
    """固定班底：名字、角色、状态、独立线程。"""

    def __init__(
        self,
        team_dir: Path,
        *,
        settings: Settings,
        tools: ToolRegistry,
    ):
        self.dir = team_dir
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "inbox").mkdir(parents=True, exist_ok=True)
        self.config_path = self.dir / "config.json"
        self.bus = MessageBus(self.dir / "inbox")
        self.settings = settings
        self.tools = tools
        self.config = self._load_config()
        self.threads: Dict[str, threading.Thread] = {}
        self.lock = threading.Lock()
        self._mark_stale_offline()

    def _load_config(self) -> Dict[str, Any]:
        if self.config_path.exists():
            try:
                return json.loads(self.config_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        return {"team_name": "tangyuan", "members": []}

    def _save_config(self) -> None:
        self.config_path.write_text(
            json.dumps(self.config, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _mark_stale_offline(self) -> None:
        changed = False
        for member in self.config.get("members", []):
            if member.get("status") in RUNTIME_STATUSES:
                member["status"] = "offline"
                changed = True
        if changed:
            self._save_config()

    def _find(self, name: str) -> Optional[Dict[str, Any]]:
        for m in self.config.get("members", []):
            if m.get("name") == name:
                return m
        return None

    def _set_status(self, name: str, status: str) -> None:
        with self.lock:
            m = self._find(name)
            if m:
                m["status"] = status
                self._save_config()

    def member_names(self) -> List[str]:
        with self.lock:
            return [m["name"] for m in self.config.get("members", [])]

    def list_all(self) -> str:
        with self.lock:
            members = self.config.get("members") or []
            if not members:
                return "暂无队友。可用 spawn_teammate 召入。"
            lines = [f"Team: {self.config.get('team_name', 'tangyuan')}"]
            for m in members:
                status = m.get("status", "?")
                note = "（需重新 spawn 才会处理 inbox）" if status == "offline" else ""
                lines.append(
                    f"  - {m.get('name')}（{m.get('role')}）：{status}{note}"
                )
            return "\n".join(lines)

    def spawn(self, name: str, role: str, prompt: str) -> str:
        name = (name or "").strip()
        role = (role or "").strip() or "teammate"
        prompt = (prompt or "").strip()
        if not name:
            return "Error: name 不能为空"
        if not prompt:
            return "Error: prompt 不能为空（初次任务说明）"

        with self.lock:
            member = self._find(name)
            running = self.threads.get(name)
            if member and running and running.is_alive():
                self.bus.send("lead", name, prompt)
                member["role"] = role
                member["status"] = "working"
                self._save_config()
                return f"'{name}' 已在队中，新差事已送入 inbox"
            if member:
                member["role"] = role
                member["status"] = "working"
            else:
                self.config.setdefault("members", []).append(
                    {"name": name, "role": role, "status": "working"}
                )
            self._save_config()

        thread = threading.Thread(
            target=self._teammate_loop,
            args=(name, role, prompt),
            daemon=True,
            name=f"tangyuan-teammate-{name}",
        )
        self.threads[name] = thread
        thread.start()
        return f"已召入/唤回队友 '{name}'（角色：{role}），线程已启动"

    def _teammate_loop(self, name: str, role: str, prompt: str) -> None:
        client = OpenAI(
            api_key=self.settings.api_key,
            base_url=self.settings.base_url,
        )
        system = (
            f"你是汤圆 Agent Team 的固定队友，名叫「{name}」，角色：{role}。\n"
            f"工作区：{self.settings.resolve_workspace()}\n"
            "你不是一次性子代理，而是持久成员：办完当前差事后进入等待，继续处理 inbox。\n"
            "规则：\n"
            "1. 用工具取证，不要编造。\n"
            "2. 办完后必须用 send_message 向 lead 回禀简短结果。\n"
            "3. 可用 read_inbox；收到 shutdown_request 时回 shutdown_response 后停止。\n"
            "4. 不要试图 spawn 新队友或改主计划。\n"
        )
        allowed = [t for t in _TEAMMATE_TOOLS if t in self.tools.names()]
        schemas = self.tools.schemas(allowed) + [
            {
                "type": "function",
                "function": {
                    "name": "send_message",
                    "description": "给 lead 或其他队友发 inbox 消息。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "to": {"type": "string"},
                            "content": {"type": "string"},
                            "msg_type": {
                                "type": "string",
                                "enum": sorted(VALID_MSG_TYPES),
                            },
                        },
                        "required": ["to", "content"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "read_inbox",
                    "description": "读取并清空自己的 inbox。",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
        ]
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]
        has_work = True

        while True:
            inbox = self.bus.read_inbox(name)
            for msg in inbox:
                if msg.get("type") == "shutdown_request":
                    self.bus.send(
                        name,
                        msg.get("from", "lead"),
                        "准许退下，队友线程即将停止。",
                        "shutdown_response",
                    )
                    self._set_status(name, "shutdown")
                    return
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "<inbox>\n"
                            + json.dumps(msg, ensure_ascii=False, indent=2)
                            + "\n</inbox>"
                        ),
                    }
                )
                has_work = True

            if not has_work:
                self._set_status(name, "idle")
                time.sleep(1.0)
                continue

            self._set_status(name, "working")
            for _turn in range(20):
                try:
                    resp = client.chat.completions.create(
                        model=self.settings.model,
                        messages=messages,
                        tools=schemas,
                        tool_choice="auto",
                        temperature=self.settings.temperature,
                    )
                    record_usage_from_response(
                        resp,
                        model=self.settings.model,
                        workspace=str(self.settings.resolve_workspace()),
                    )
                except Exception as e:  # noqa: BLE001
                    self.bus.send(name, "lead", f"队友 {name} 调用模型失败：{e}")
                    self._set_status(name, "idle")
                    has_work = False
                    break

                msg = resp.choices[0].message
                tool_calls = msg.tool_calls or []
                assistant: Dict[str, Any] = {
                    "role": "assistant",
                    "content": msg.content or "",
                }
                if tool_calls:
                    assistant["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments or "{}",
                            },
                        }
                        for tc in tool_calls
                    ]
                messages.append(assistant)

                if not tool_calls:
                    final = (msg.content or "").strip()
                    if final:
                        self.bus.send(name, "lead", final)
                    self._set_status(name, "idle")
                    has_work = False
                    break

                for tc in tool_calls:
                    tname = tc.function.name
                    try:
                        args = json.loads(tc.function.arguments or "{}")
                    except json.JSONDecodeError:
                        result = json.dumps(
                            {"ok": False, "error": "工具参数不是合法 JSON"},
                            ensure_ascii=False,
                        )
                    else:
                        result = self._exec(name, tname, args, allowed)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": result,
                        }
                    )
            else:
                self.bus.send(
                    name,
                    "lead",
                    f"队友 {name} 达到本轮 20 次调用上限，已暂停等待下一步指令。",
                )
                self._set_status(name, "idle")
                has_work = False

    def _exec(
        self,
        sender: str,
        tool_name: str,
        args: Dict[str, Any],
        allowed: List[str],
    ) -> str:
        if tool_name == "send_message":
            return self.bus.send(
                sender,
                args.get("to", "lead"),
                args.get("content", ""),
                args.get("msg_type") or "message",
            )
        if tool_name == "read_inbox":
            return json.dumps(
                self.bus.read_inbox(sender),
                ensure_ascii=False,
                indent=2,
            )
        if tool_name not in allowed:
            return json.dumps(
                {"ok": False, "error": f"队友无权使用工具: {tool_name}"},
                ensure_ascii=False,
            )
        return self.tools.call(tool_name, args)


def team_dir_for(workspace: Path) -> Path:
    return workspace.resolve() / ".tangyuan" / "team"
