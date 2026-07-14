"""评测执行器：在隔离临时 workspace 中跑用例并产出报告。"""

from __future__ import annotations

import shutil
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tangyuan.config import load_settings
from tangyuan.eval.assertions import Assertion, AssertResult
from tangyuan.tools import build_default_tools
from tangyuan.trace import TraceLogger

# 用例 setup：在临时 workspace 里准备文件
SetupFn = Callable[[Path], None]


@dataclass
class EvalCase:
    id: str
    title: str
    prompt: str
    assertions: list[Assertion]
    setup: SetupFn | None = None
    network: bool = False  # 是否依赖外网
    timeout_seconds: int = 120
    tags: list[str] = field(default_factory=list)


@dataclass
class CaseResult:
    case_id: str
    title: str
    passed: bool
    duration_sec: float
    assertions: list[dict[str, Any]] = field(default_factory=list)
    reply: str = ""
    error: str | None = None


@dataclass
class EvalResult:
    total: int
    passed: int
    failed: int
    skipped: int
    duration_sec: float
    cases: list[CaseResult] = field(default_factory=list)


def _setup_workspace(case: EvalCase, tmpdir: Path) -> None:
    """在临时目录准备用例初始状态。"""
    # 总是初始化一个 git 仓库，让 git_ 工具可用
    import subprocess
    try:
        subprocess.run(["git", "init", "-q"], cwd=str(tmpdir), capture_output=True, timeout=5)
        subprocess.run(["git", "config", "user.email", "tangyuan@local"], cwd=str(tmpdir), capture_output=True, timeout=5)
        subprocess.run(["git", "config", "user.name", "tangyuan"], cwd=str(tmpdir), capture_output=True, timeout=5)
    except Exception:  # noqa: BLE001
        pass
    if case.setup is not None:
        case.setup(tmpdir)
    # 初始 commit，让 git log 等可用
    try:
        subprocess.run(["git", "add", "-A"], cwd=str(tmpdir), capture_output=True, timeout=5)
        subprocess.run(
            ["git", "commit", "-q", "-m", "init"],
            cwd=str(tmpdir),
            capture_output=True,
            input="",
            text=True,
            timeout=5,
        )
    except Exception:  # noqa: BLE001
        pass


def _make_silent_event() -> Callable:
    """静默事件回调：评测时不打印。"""
    return lambda *_a, **_k: None


def run_single(case: EvalCase, *, model: str | None = None, yes: bool = True) -> CaseResult:
    """跑单个用例。"""
    import tangyuan.memory.paths as mem_paths
    from tangyuan.agent import TangyuanAgent  # 延迟导入，避免循环

    start = time.time()
    tmpdir = Path(tempfile.mkdtemp(prefix=f"ty_eval_{case.id}_"))
    # 让全局记忆目录也指向临时目录，避免污染真实 ~/.tangyuan/
    fake_global = tmpdir / "_global_memory"
    fake_global.mkdir(parents=True, exist_ok=True)
    original_global = mem_paths.global_memory_dir
    mem_paths.global_memory_dir = lambda: fake_global  # type: ignore
    try:
        _setup_workspace(case, tmpdir)
        settings = load_settings(workspace=str(tmpdir), model=model)
        settings.max_steps = 30
        tools = build_default_tools(
            tmpdir,
            settings.shell_timeout,
            confirm=None,
            confirm_writes=False,
            confirm_shell=False,
            settings=settings,
        )
        trace = TraceLogger(tmpdir)
        agent = TangyuanAgent(settings, tools, trace, on_event=_make_silent_event())
        try:
            reply = agent.ask(case.prompt)
        except Exception as e:  # noqa: BLE001
            return CaseResult(
                case_id=case.id,
                title=case.title,
                passed=False,
                duration_sec=time.time() - start,
                reply="",
                error=f"agent 抛异常: {e}",
            )

        # 跑断言
        assertions_meta: list[dict[str, Any]] = []
        all_pass = True
        for idx, assertion in enumerate(case.assertions):
            try:
                r: AssertResult = assertion(tmpdir, reply)
            except Exception as e:  # noqa: BLE001
                r = AssertResult(False, f"断言异常: {e}")
            if not r.ok:
                all_pass = False
            assertions_meta.append(
                {
                    "index": idx,
                    "ok": r.ok,
                    "detail": r.detail,
                }
            )
        return CaseResult(
            case_id=case.id,
            title=case.title,
            passed=all_pass,
            duration_sec=time.time() - start,
            assertions=assertions_meta,
            reply=reply[:2000],
        )
    finally:
        mem_paths.global_memory_dir = original_global  # type: ignore
        # 保留临时目录以便调试？为了 CI 简洁，直接清理。
        shutil.rmtree(tmpdir, ignore_errors=True)


def run_eval(
    cases: list[EvalCase],
    *,
    model: str | None = None,
    skip_network: bool = False,
    only: list[str] | None = None,
    stop_on_fail: bool = False,
    on_progress: Callable[[CaseResult, int, int], None] | None = None,
) -> EvalResult:
    """跑评测集，返回汇总。"""
    start = time.time()
    results: list[CaseResult] = []
    skipped = 0
    for i, case in enumerate(cases, 1):
        if only and case.id not in only:
            skipped += 1
            continue
        if skip_network and case.network:
            skipped += 1
            results.append(
                CaseResult(
                    case_id=case.id,
                    title=case.title,
                    passed=False,
                    duration_sec=0.0,
                    error="skipped (network)",
                )
            )
            continue
        res = run_single(case, model=model)
        results.append(res)
        if on_progress:
            on_progress(res, i, len(cases))
        if stop_on_fail and not res.passed:
            break
    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)
    return EvalResult(
        total=len(results),
        passed=passed,
        failed=failed,
        skipped=skipped,
        duration_sec=time.time() - start,
        cases=results,
    )


def render_report(result: EvalResult, *, model: str = "") -> str:
    """渲染 markdown 报告。"""
    lines: list[str] = []
    lines.append("# 汤圆评测报告")
    lines.append("")
    if model:
        lines.append(f"- 模型：`{model}`")
    lines.append(f"- 总用例：{result.total}")
    lines.append(f"- 通过：{result.passed}")
    lines.append(f"- 失败：{result.failed}")
    lines.append(f"- 跳过：{result.skipped}")
    lines.append(f"- 耗时：{result.duration_sec:.1f}s")
    success_rate = (result.passed / result.total * 100) if result.total else 0
    lines.append(f"- 成功率：**{success_rate:.1f}%**")
    lines.append("")
    lines.append("| # | id | 标题 | 结果 | 耗时 |")
    lines.append("|---|----|------|------|------|")
    for i, c in enumerate(result.cases, 1):
        status = "✅" if c.passed else "❌"
        lines.append(
            f"| {i} | `{c.case_id}` | {c.title} | {status} | {c.duration_sec:.1f}s |"
        )
    lines.append("")
    # 失败详情
    failures = [c for c in result.cases if not c.passed and not c.error]
    if failures:
        lines.append("## 失败详情")
        lines.append("")
        for c in failures:
            lines.append(f"### `{c.case_id}` — {c.title}")
            lines.append("")
            for a in c.assertions:
                if not a["ok"]:
                    lines.append(f"- ❌ {a['detail']}")
            if c.reply:
                lines.append("")
                lines.append("<details><summary>回复（前 500 字）</summary>")
                lines.append("")
                lines.append("```")
                lines.append(c.reply[:500])
                lines.append("```")
                lines.append("")
                lines.append("</details>")
            lines.append("")
    errors = [c for c in result.cases if c.error]
    if errors:
        lines.append("## 异常用例")
        lines.append("")
        for c in errors:
            lines.append(f"- `{c.case_id}`：{c.error}")
        lines.append("")
    return "\n".join(lines)


def save_report(result: EvalResult, path: Path, *, model: str = "") -> None:
    text = render_report(result, model=model)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
