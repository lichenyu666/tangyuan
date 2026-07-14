from __future__ import annotations

import json
import re
from typing import Any

from openai import OpenAI

from tangyuan.agent.plan import TaskPlan
from tangyuan.config import Settings
from tangyuan.hooks import HookDecision, build_default_hooks
from tangyuan.memory import (
    append_daily_log,
    append_history,
    append_tokens,
    estimate_messages_chars,
    record_usage_from_response,
    write_memory,
)
from tangyuan.prompts import load_compact_prompt, load_distill_prompt
from tangyuan.prompts.assemble import assemble_system_prompt
from tangyuan.tools import ToolRegistry, build_user_message
from tangyuan.tools.register_plan import ensure_plan_tool
from tangyuan.trace import TraceLogger

# 有未完成计划时：连续这么多步没有任何「完成/取消」进展 → 提醒回退换路径
_STALL_LIMIT = 8
# 结束门禁催办未完成项的最大次数（防死循环）
_MAX_PLAN_STOP_PUSHES = 3


class TangyuanAgent:
    """支持多轮会话的终端 Agent。"""

    def __init__(
        self,
        settings: Settings,
        tools: ToolRegistry,
        trace: TraceLogger,
        on_event: Any | None = None,
        forced_skill_id: str | None = None,
    ):
        if not settings.api_key:
            raise ValueError(
                "缺少 TANGYUAN_API_KEY。请把密钥写到 ~/.tangyuan/.env "
                "（或当前目录 / 仓库根目录的 .env）。可参考 .env.example。"
            )
        self.settings = settings
        self.tools = tools
        self.trace = trace
        self.on_event = on_event or (lambda *_a, **_k: None)
        self.client = OpenAI(api_key=settings.api_key, base_url=settings.base_url)
        self.forced_skill_id = forced_skill_id
        self.plan = TaskPlan()
        ensure_plan_tool(self.tools, self.plan)
        ws = settings.resolve_workspace()
        self.hooks = build_default_hooks(
            audit_path=ws / ".tangyuan" / "hooks_audit.jsonl"
        )
        self.messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._system_prompt()},
        ]

    def _system_prompt(self) -> str:
        ws = self.settings.resolve_workspace()
        return assemble_system_prompt(
            ws,
            forced_skill_id=self.forced_skill_id,
            plan=self.plan,
        )

    def refresh_system_prompt(self) -> None:
        """记忆/Skill 变更后刷新 system 消息。"""
        content = self._system_prompt()
        if self.messages and self.messages[0].get("role") == "system":
            self.messages[0]["content"] = content
        else:
            self.messages.insert(0, {"role": "system", "content": content})

    def set_forced_skill(self, skill_id: str | None) -> None:
        """手动指定/取消 Skill，并刷新系统提示。"""
        self.forced_skill_id = skill_id
        self.refresh_system_prompt()

    def ask(self, task: str) -> str:
        ws = self.settings.resolve_workspace()
        self._maybe_compact_session()
        user_content = build_user_message(task, ws)
        self.messages.append({"role": "user", "content": user_content})
        self.trace.log("user", task=task, forced_skill=self.forced_skill_id)
        append_history(
            {
                "role": "user",
                "workspace": str(ws),
                "content": task[:4000],
            }
        )
        return self._loop()

    def run(self, task: str) -> str:
        return self.ask(task)

    def _non_system_count(self) -> int:
        return sum(1 for m in self.messages if m.get("role") != "system")

    def _maybe_compact_session(self) -> None:
        """工作记忆过长时，把旧消息压成一条会话摘要。"""
        threshold = self.settings.compact_after_messages
        keep = self.settings.compact_keep_recent
        chars = estimate_messages_chars(self.messages)
        by_count = self._non_system_count() >= threshold
        by_chars = chars >= self.settings.compact_after_chars
        if not (by_count or by_chars):
            return

        system = self.messages[0] if self.messages and self.messages[0].get("role") == "system" else None
        rest = self.messages[1:] if system else list(self.messages)
        if len(rest) <= keep:
            return

        old, recent = rest[:-keep], rest[-keep:]
        digest = _render_messages_digest(old, max_chars=16000)
        plan_digest = self.plan.render_digest()
        if plan_digest and plan_digest != "(空)":
            digest = f"【当前任务计划】\n{plan_digest}\n\n{digest}"
        summary_text = self._summarize_session(digest)
        plan_block = ""
        if self.plan.items:
            plan_block = (
                "\n\n【请继续执行的任务计划】\n"
                + self.plan.render_prompt_section()
            )
        compact_msg = {
            "role": "assistant",
            "content": (
                "【会话摘要 — 此前对话已压缩，请继承其中的结论与未竟事项】\n"
                f"{summary_text}"
                f"{plan_block}"
            ),
        }
        self.messages = ([system] if system else []) + [compact_msg] + recent
        self.trace.log(
            "compact",
            old_messages=len(old),
            kept=len(recent),
            chars_before=estimate_messages_chars(old),
            trigger="chars" if by_chars and not by_count else "count",
        )
        self.on_event("compact", old=len(old), kept=len(recent))
        # 压缩后顺手蒸馏项目事实（不写用户隐私）
        self.distill_project_memory(source_digest=summary_text)

    def _summarize_session(self, digest: str) -> str:
        try:
            resp = self.client.chat.completions.create(
                model=self.settings.model,
                messages=[
                    {
                        "role": "system",
                        "content": load_compact_prompt(),
                    },
                    {"role": "user", "content": digest},
                ],
                temperature=0.1,
            )
            record_usage_from_response(
                resp,
                model=self.settings.model,
                workspace=str(self.settings.resolve_workspace()),
            )
            text = (resp.choices[0].message.content or "").strip()
            return text or digest[:800]
        except Exception as e:  # noqa: BLE001
            self.trace.log("compact_error", error=str(e))
            return digest[:800] + "\n…(摘要失败，保留摘录前部)"

    def distill_project_memory(self, source_digest: str | None = None) -> list[str]:
        """
        从当前会话（或给定摘要）提炼 0～3 条项目级事实写入 project.md。
        只写 bucket=project，不自动写用户画像。
        """
        ws = self.settings.resolve_workspace()
        if source_digest:
            material = source_digest
        else:
            material = _render_messages_digest(
                [m for m in self.messages if m.get("role") != "system"],
                max_chars=10000,
            )
        if len(material.strip()) < 80:
            return []

        try:
            resp = self.client.chat.completions.create(
                model=self.settings.model,
                messages=[
                    {
                        "role": "system",
                        "content": load_distill_prompt(),
                    },
                    {"role": "user", "content": material},
                ],
                temperature=0.1,
            )
            record_usage_from_response(
                resp,
                model=self.settings.model,
                workspace=str(ws),
            )
            raw = (resp.choices[0].message.content or "").strip()
            facts = _parse_fact_json(raw)
        except Exception as e:  # noqa: BLE001
            self.trace.log("distill_error", error=str(e))
            return []

        written: list[str] = []
        for item in facts[:3]:
            topic = (item.get("topic") or "").strip() or None
            fact = (item.get("fact") or "").strip()
            if not fact:
                continue
            msg = write_memory(ws, fact, bucket="project", topic=topic)
            written.append(msg)
            self.trace.log("distill", topic=topic, fact=fact)
        if written:
            # 同时记入今日日记，方便按日回看
            try:
                append_daily_log(
                    "\n".join(f"- {w}" for w in written),
                    heading="项目蒸馏",
                )
            except Exception:  # noqa: BLE001
                pass
            self.refresh_system_prompt()
            self.on_event("distill", items=written)
        return written

    def _loop(self) -> str:
        final_text = ""
        stall_steps = 0
        last_progress = self.plan.progress_key()
        plan_stop_pushes = 0
        for step in range(1, self.settings.max_steps + 1):
            self.on_event("step", step=step, max_steps=self.settings.max_steps)
            self.trace.log("step", step=step)

            content_buf, raw_tool_calls, usage = self._stream_completion()
            if usage is not None:
                append_tokens(
                    model=self.settings.model,
                    prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                    completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
                    total_tokens=getattr(usage, "total_tokens", 0) or 0,
                    workspace=str(self.settings.resolve_workspace()),
                )

            assistant_msg: dict[str, Any] = {
                "role": "assistant",
                "content": content_buf or "",
            }
            if raw_tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["function"]["name"],
                            "arguments": tc["function"]["arguments"] or "{}",
                        },
                    }
                    for tc in raw_tool_calls
                ]
            self.messages.append(assistant_msg)

            if not raw_tool_calls:
                final_text = (content_buf or "").strip()
                self.on_event("stream_end")
                stop_ctx: dict[str, Any] = {
                    "reply": final_text,
                    "plan": self.plan,
                    "retry": plan_stop_pushes,
                }
                decision = self.hooks.emit("on_stop", stop_ctx)
                if (
                    isinstance(decision, HookDecision)
                    and decision.action == "block"
                    and plan_stop_pushes < _MAX_PLAN_STOP_PUSHES
                ):
                    plan_stop_pushes += 1
                    self.messages.append(
                        {"role": "user", "content": decision.reason}
                    )
                    self.trace.log(
                        "plan_stop_gate",
                        push=plan_stop_pushes,
                        open=self.plan.render_open_digest(),
                    )
                    self.on_event(
                        "plan_stall",
                        open=self.plan.render_open_digest(),
                        items=self.plan.to_dicts(),
                        gate=True,
                    )
                    continue

                # 办妥：清空计划，防止串到下一轮差事
                if self.plan.items and not self.plan.open_items():
                    self.plan.clear()
                    self.refresh_system_prompt()
                    self.on_event("plan", items=[])
                    self.trace.log("plan_cleared")

                self.trace.log("final", content=final_text)
                self.on_event("final", content=final_text)
                append_history(
                    {
                        "role": "assistant",
                        "workspace": str(self.settings.resolve_workspace()),
                        "content": final_text[:8000],
                    }
                )
                break

            self.on_event("stream_end")

            for tc in raw_tool_calls:
                name = tc["function"]["name"]
                args: dict[str, Any] = {}
                try:
                    args = json.loads(tc["function"]["arguments"] or "{}")
                except json.JSONDecodeError:
                    result = json.dumps(
                        {"ok": False, "error": "工具参数不是合法 JSON"},
                        ensure_ascii=False,
                    )
                    self.trace.log("error", tool=name, error="invalid json args")
                else:
                    result = self._invoke_tool(name, args)

                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result,
                    }
                )

            before_progress = last_progress
            stall_steps, last_progress = self._track_plan_progress(
                stall_steps, last_progress
            )
            if _plan_advanced(before_progress, last_progress) or (
                self.plan.items and not self.plan.open_items()
            ):
                plan_stop_pushes = 0
        else:
            final_text = (
                f"已达最大步数 {self.settings.max_steps}，"
                "请缩小任务或提高 TANGYUAN_MAX_STEPS。"
            )
            open_items = self.plan.open_items()
            if open_items:
                final_text += "\n未完成步骤：\n" + "\n".join(
                    f"- [{i.status}] {i.id}: {i.content}" for i in open_items
                )
            self.trace.log("max_steps", content=final_text)
            self.on_event("final", content=final_text)
            self.messages.append({"role": "assistant", "content": final_text})

        self.trace.log("summary", **self.trace.summary())
        return final_text

    def _stream_completion(self) -> tuple[str, list, Any]:
        """
        流式调用 LLM，累积 content 与 tool_calls，逐 delta 推到 UI。
        返回 (content, tool_calls, usage)。
        """
        stream = self.client.chat.completions.create(
            model=self.settings.model,
            messages=self.messages,
            tools=self.tools.schemas(),
            tool_choice="auto",
            temperature=self.settings.temperature,
            stream=True,
            stream_options={"include_usage": True},
        )

        content_buf = ""
        tool_calls_buf: dict[int, dict[str, Any]] = {}
        usage_obj: Any = None
        started = False

        for chunk in stream:
            if getattr(chunk, "usage", None):
                usage_obj = chunk.usage
            choices = getattr(chunk, "choices", None) or []
            if not choices:
                continue
            delta = choices[0].delta
            piece = getattr(delta, "content", None)
            if piece:
                if not started:
                    started = True
                    self.on_event("stream_start")
                content_buf += piece
                self.on_event("stream_delta", delta=piece)
            tc_deltas = getattr(delta, "tool_calls", None) or []
            for tc in tc_deltas:
                idx = tc.index
                if idx not in tool_calls_buf:
                    tool_calls_buf[idx] = {
                        "id": "",
                        "type": "function",
                        "function": {"name": "", "arguments": ""},
                    }
                if tc.id:
                    tool_calls_buf[idx]["id"] = tc.id
                fn = tc.function
                if fn is not None:
                    if fn.name:
                        tool_calls_buf[idx]["function"]["name"] += fn.name
                    if fn.arguments:
                        tool_calls_buf[idx]["function"]["arguments"] += fn.arguments

        raw_tool_calls = [tool_calls_buf[k] for k in sorted(tool_calls_buf)]
        return content_buf, raw_tool_calls, usage_obj

    def _invoke_tool(self, name: str, args: dict[str, Any]) -> str:
        """工具调用走 Hook：before → call → after。"""
        ctx: dict[str, Any] = {"name": name, "input": dict(args), "plan": self.plan}
        decision = self.hooks.emit(
            "before_tool_call", ctx, tool_matcher=name
        )
        if isinstance(decision, HookDecision):
            if decision.is_blocking:
                return json.dumps(
                    {"ok": False, "error": decision.to_message()},
                    ensure_ascii=False,
                )
            if decision.action == "ask":
                return json.dumps(
                    {
                        "ok": False,
                        "error": decision.to_message() + "（未确认，已取消）",
                    },
                    ensure_ascii=False,
                )
            if decision.updated_input is not None:
                args = decision.updated_input
        elif isinstance(decision, str):
            return decision

        args = ctx.get("input", args)
        self.on_event("tool_call", name=name, args=args)
        self.trace.log("tool_call", name=name, args=args)
        result = self.tools.call(name, args)
        ctx["output"] = result
        self.hooks.emit("after_tool_call", ctx, tool_matcher=name)
        result = str(ctx.get("output", result))
        self.trace.log("tool_result", name=name, result=_truncate(result))
        self.on_event("tool_result", name=name, result=_truncate(result, 500))
        if name == "remember":
            self.refresh_system_prompt()
        elif name == "update_plan":
            self.refresh_system_prompt()
            self.on_event("plan", items=self.plan.to_dicts())
        elif name == "dispatch_subagent":
            self.on_event("subagent", preview=_truncate(result, 200))
        return result

    def _track_plan_progress(
        self, stall_steps: int, last_progress: tuple
    ) -> tuple[int, tuple]:
        """
        先看未完成项：
        - 无未完成 → 重置计数
        - 有完成/取消进展 → 重置计数
        - 未完成且连续多步无进展 → 回退提醒后重置计数（避免每步刷屏）
        """
        open_items = self.plan.open_items()
        now = self.plan.progress_key()

        if not open_items:
            return 0, now

        if _plan_advanced(last_progress, now):
            return 0, now

        stall_steps += 1
        if stall_steps < _STALL_LIMIT:
            return stall_steps, now

        open_lines = "\n".join(
            f"- [{i.status}] `{i.id}` {i.content}" for i in open_items
        )
        nudge = (
            "【系统提醒】请先核对未完成计划项，当前已连续多步没有勾完成/取消：\n"
            f"{open_lines}\n"
            "若当前路径走不通：用 update_plan 回退（改路径、标阻塞或 cancelled），"
            "换工具/思路再试；不要在同一未完成项上空转。"
            "若某步其实已办成：立刻 update_plan 勾 completed。"
        )
        self.messages.append({"role": "user", "content": nudge})
        self.trace.log(
            "plan_stall",
            open=self.plan.render_open_digest(),
            stall_steps=stall_steps,
        )
        self.on_event(
            "plan_stall",
            open=self.plan.render_open_digest(),
            items=self.plan.to_dicts(),
        )
        return 0, now


def _plan_advanced(before: tuple, after: tuple) -> bool:
    """是否出现实质进展：新增 completed 或 cancelled。"""
    b_completed, b_cancelled, _b_in, _b_pending = before
    a_completed, a_cancelled, _a_in, _a_pending = after
    if set(a_completed) - set(b_completed):
        return True
    if set(a_cancelled) - set(b_cancelled):
        return True
    return False


def _parse_fact_json(raw: str) -> list[dict[str, str]]:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\[.*\]", raw, re.S)
        if not m:
            return []
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return []
    if not isinstance(data, list):
        return []
    out: list[dict[str, str]] = []
    for item in data:
        if isinstance(item, dict) and item.get("fact"):
            out.append(
                {
                    "topic": str(item.get("topic") or ""),
                    "fact": str(item["fact"]),
                }
            )
    return out


def _render_messages_digest(messages: list[dict[str, Any]], max_chars: int = 12000) -> str:
    parts: list[str] = []
    for m in messages:
        role = m.get("role", "?")
        content = m.get("content") or ""
        if role == "tool":
            # 尽量保留路径/命令关键信息
            content = _preserve_paths(_truncate(str(content), 1200))
            parts.append(f"[tool] {content}")
        elif role == "assistant" and m.get("tool_calls"):
            names = []
            for tc in m["tool_calls"]:
                try:
                    names.append(tc["function"]["name"])
                    args = tc["function"].get("arguments") or ""
                    if "path" in args or "command" in args:
                        names[-1] += f"({_truncate(args, 120)})"
                except Exception:  # noqa: BLE001
                    pass
            snippet = _truncate(str(content), 400) if content else ""
            parts.append(f"[assistant/tools:{','.join(names)}] {snippet}")
        else:
            parts.append(f"[{role}] {_truncate(str(content), 1200)}")
    text = "\n".join(parts)
    if len(text) > max_chars:
        return text[:max_chars] + "\n…(digest truncated)"
    return text


def _preserve_paths(text: str) -> str:
    """若截断后仍含 path/command 字段，原样返回；否则原样。"""
    return text


def _truncate(text: str, n: int = 4000) -> str:
    if len(text) <= n:
        return text
    return text[:n] + f"...<truncated {len(text) - n} chars>"
