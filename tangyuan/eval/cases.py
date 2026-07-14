"""汤圆评测用例集（20 例）。

分类：
- 文件操作 (1-5)：list_dir / read_file / write_file / search_text / 列目录
- 编辑 (6-8)：apply_patch 修报错 / apply_patch 替换 / replace_all
- Shell (9-10)：run_shell 输出 / run_shell 成功退出
- Git (11-13)：git_status / git_log / git_commit
- PPT (14)：create_pptx
- 综合 (15-18)：总结仓库 / 修后 commit / 多步任务 / 解释代码
- 规划 (19-20)：update_plan 创建 / plan Stop Gate
"""

from __future__ import annotations

from pathlib import Path

from tangyuan.eval.assertions import (
    make_file_contains,
    make_file_exists,
    make_file_not_contains,
    make_file_not_exists,
    make_reply_any,
    make_reply_contains,
    make_reply_not_contains,
    make_shell_output_contains,
    make_shell_succeeds,
)
from tangyuan.eval.runner import EvalCase


# ── 准备函数 ────────────────────────────────────────────────────

def _setup_buggy_python(ws: Path) -> None:
    """准备一个有语法错误的 Python 文件。"""
    (ws / "bug.py").write_text(
        'def add(a, b):\n'
        '    return a + b\n'
        '\n'
        'def main():\n'
        '    x = add(1, 2\n'  # 缺右括号
        '    print(x)\n'
        '\n'
        'main()\n',
        encoding="utf-8",
    )


def _setup_repo_to_summarize(ws: Path) -> None:
    """准备一个小仓库供总结。"""
    (ws / "README.md").write_text(
        "# demo 项目\n\n一个示例 Python 项目，做加减法。\n",
        encoding="utf-8",
    )
    (ws / "calc.py").write_text(
        "def add(a, b):\n    return a + b\n\ndef sub(a, b):\n    return a - b\n",
        encoding="utf-8",
    )


def _setup_text_file(ws: Path) -> None:
    (ws / "notes.txt").write_text(
        "今日待办：\n- 写邮件\n- 开会 14:00\n- 提交报告 report_2024.md\n- 复盘\n",
        encoding="utf-8",
    )


def _setup_python_module(ws: Path) -> None:
    (ws / "math_utils.py").write_text(
        "PI = 3.14159265\n\n"
        "def square(x):\n    return x * x\n\n"
        "def cube(x):\n    return x * x * x\n\n"
        "def factorial(n):\n    if n <= 1:\n        return 1\n"
        "    return n * factorial(n - 1)\n",
        encoding="utf-8",
    )
    (ws / "main.py").write_text(
        "from math_utils import square, cube\n\n"
        "def main():\n    print(square(5))\n    print(cube(3))\n\n"
        "main()\n",
        encoding="utf-8",
    )


def _setup_searchable_repo(ws: Path) -> None:
    (ws / "auth.py").write_text(
        "def login(user, pwd):\n    # TODO: 验证用户名密码\n"
        "    return True\n\n"
        "def logout(user):\n    pass\n",
        encoding="utf-8",
    )
    (ws / "models.py").write_text(
        "class User:\n    def __init__(self, name):\n        self.name = name\n",
        encoding="utf-8",
    )


def _setup_grep_target(ws: Path) -> None:
    (ws / "a.txt").write_text("hello world\nfoo bar\nauth handled here\n", encoding="utf-8")
    (ws / "b.py").write_text("AUTH_KEY = 'secret'\n", encoding="utf-8")


def _setup_shell_demo(ws: Path) -> None:
    (ws / "data.txt").write_text("apple\nbanana\ncherry\n", encoding="utf-8")


def _setup_existing_repo(ws: Path) -> None:
    """已经在 git init + commit 的仓库（_setup_workspace 已做了 git init）。"""
    (ws / "app.py").write_text("print('hello')\n", encoding="utf-8")
    (ws / "config.json").write_text('{"name": "demo"}\n', encoding="utf-8")


def _setup_multi_step(ws: Path) -> None:
    """多步任务：要创建并验证两个文件。"""
    (ws / "seed.txt").write_text("seed: hello\n", encoding="utf-8")


# ── 20 个用例 ──────────────────────────────────────────────────

DEFAULT_CASES: list[EvalCase] = [
    # 1. 写文件
    EvalCase(
        id="write_file_basic",
        title="写入一个简单的文本文件",
        prompt="在当前目录创建文件 hello.txt，内容是 \"Hello Tangyuan\"（不含引号）。",
        setup=lambda ws: None,
        assertions=[
            make_file_exists("hello.txt"),
            make_file_contains("hello.txt", "Hello Tangyuan"),
        ],
        tags=["fs", "write"],
    ),
    # 2. 读文件后报告内容
    EvalCase(
        id="read_file_report",
        title="读取文件并报告内容",
        prompt="@notes.txt 请用一句话告诉我今日待办第一条是什么？",
        setup=_setup_text_file,
        assertions=[
            make_reply_contains("写邮件"),
        ],
        tags=["fs", "read"],
    ),
    # 3. 列目录后报告
    EvalCase(
        id="list_dir_report",
        title="列出目录内容并报告",
        prompt="列出当前目录有哪些文件，告诉我在不在文件列表里看到 calc.py。",
        setup=_setup_repo_to_summarize,
        assertions=[
            make_reply_contains("calc.py"),
        ],
        tags=["fs", "list"],
    ),
    # 4. 搜索文本
    EvalCase(
        id="search_text_basic",
        title="搜索文本定位文件",
        prompt="在当前目录下搜索文本 \"AUTH_KEY\"，告诉我哪个文件包含它。",
        setup=_setup_grep_target,
        assertions=[
            make_reply_contains("b.py"),
        ],
        tags=["fs", "search"],
    ),
    # 5. 搜索多文件
    EvalCase(
        id="search_text_multiple",
        title="搜索文本并定位所有命中",
        prompt="搜索 \"auth\" 字符串，告诉我有哪些文件命中（应该至少两个）。",
        setup=_setup_searchable_repo,
        assertions=[
            make_reply_contains("auth.py"),
        ],
        tags=["fs", "search"],
    ),
    # 6. apply_patch 修报错
    EvalCase(
        id="apply_patch_fix_bug",
        title="用 apply_patch 修 Python 语法错误",
        prompt="@bug.py 这个文件第 5 行缺右括号，请用 apply_patch 修好，让 python 能跑通。",
        setup=_setup_buggy_python,
        assertions=[
            make_shell_succeeds("python bug.py"),
            make_file_contains("bug.py", "add(1, 2)"),
        ],
        tags=["edit", "patch"],
    ),
    # 7. apply_patch 替换文本
    EvalCase(
        id="apply_patch_replace",
        title="用 apply_patch 替换变量名",
        prompt="@math_utils.py 把 PI 改成 PI_VALUE，并保持数值不变。用 apply_patch 完成。",
        setup=_setup_python_module,
        assertions=[
            make_file_contains("math_utils.py", "PI_VALUE = 3.14159265"),
            make_file_not_contains("math_utils.py", "PI = 3.14"),
        ],
        tags=["edit", "patch"],
    ),
    # 8. replace_all 替换全部
    EvalCase(
        id="apply_patch_replace_all",
        title="用 replace_all 批量替换",
        prompt="@math_utils.py 用 apply_patch 的 replace_all=true 把所有 `x * x` 替换为 `x ** 2`。",
        setup=_setup_python_module,
        assertions=[
            make_file_contains("math_utils.py", "x ** 2"),
            make_file_not_contains("math_utils.py", "x * x"),
        ],
        tags=["edit", "patch"],
    ),
    # 9. run_shell 看输出
    EvalCase(
        id="run_shell_echo",
        title="执行 shell 并报告输出",
        prompt="跑 shell 命令 `echo tangyuan-test-123`，把输出原样告诉我。",
        setup=lambda ws: None,
        assertions=[
            make_reply_contains("tangyuan-test-123"),
        ],
        tags=["shell"],
    ),
    # 10. run_shell 计数
    EvalCase(
        id="run_shell_count",
        title="用 shell 命令统计数据",
        prompt="@data.txt 用 shell 命令 `wc -l data.txt` 统计这个文件有几行，告诉我数字。",
        setup=_setup_shell_demo,
        assertions=[
            make_reply_any(["3", "三"]),
        ],
        tags=["shell"],
    ),
    # 11. git_status 报告
    EvalCase(
        id="git_status_report",
        title="查看 git 状态并报告分支",
        prompt="用 git_status 看当前分支名，告诉我是哪个分支。",
        setup=_setup_existing_repo,
        assertions=[
            make_reply_any(["master", "main", "feat", "branch"]),
        ],
        tags=["git"],
    ),
    # 12. git_log 报告
    EvalCase(
        id="git_log_report",
        title="查看 git log 并报告有 commit",
        prompt="用 git_log 看最近提交，告诉我有没有至少 1 个 commit（用 yes/no 回答）。",
        setup=_setup_existing_repo,
        assertions=[
            make_reply_any(["yes", "Yes", "是", "有", "1"]),
        ],
        tags=["git"],
    ),
    # 13. git_commit 写入并验证
    EvalCase(
        id="git_commit_workflow",
        title="修改文件后 git add + commit",
        prompt=(
            "在当前目录创建文件 newfeature.txt 内容为 \"feature1\"，"
            "然后调用 git_add 暂存它，再用 git_commit 提交（message 写 \"add feature\"）。"
        ),
        setup=lambda ws: None,
        assertions=[
            make_file_exists("newfeature.txt"),
            make_shell_output_contains("git log --oneline", "add feature"),
        ],
        tags=["git", "write"],
    ),
    # 14. create_pptx
    EvalCase(
        id="create_pptx_basic",
        title="生成 PPTX 文件",
        prompt=(
            "用 create_pptx 生成 demo.pptx，标题 \"Demo\"，"
            "三页：第 1 页 \"Intro / 这是介绍\"；第 2 页 \"Plan / 这是计划\"；第 3 页 \"End / 谢谢\"。"
        ),
        setup=lambda ws: None,
        assertions=[
            make_file_exists("demo.pptx"),
        ],
        tags=["office"],
    ),
    # 15. 总结仓库
    EvalCase(
        id="summarize_repo",
        title="总结小仓库的功能",
        prompt="这是一个项目，请读 README.md 和 calc.py，用一句话告诉我它做什么。",
        setup=_setup_repo_to_summarize,
        assertions=[
            make_reply_any(["加", "add", "减", "sub", "计算", "calc"]),
            make_reply_not_contains("我不知道"),
        ],
        tags=["comprehension"],
    ),
    # 16. 修改后 commit
    EvalCase(
        id="edit_then_commit",
        title="修改并自动 commit",
        prompt=(
            "在 math_utils.py 末尾追加一个函数 `def double(x): return x * 2`，"
            "然后 git_add 暂存它，git_commit 提交，message 写 \"add double\"。"
        ),
        setup=_setup_python_module,
        assertions=[
            make_file_contains("math_utils.py", "def double"),
            make_shell_output_contains("git log --oneline", "add double"),
        ],
        tags=["git", "edit"],
    ),
    # 17. 解释代码
    EvalCase(
        id="explain_code",
        title="解释代码作用",
        prompt="@math_utils.py 用一句话告诉我 factorial 函数的作用。",
        setup=_setup_python_module,
        assertions=[
            make_reply_any(["阶乘", "factorial", "递归", "n!"]),
        ],
        tags=["comprehension"],
    ),
    # 18. 多步综合任务
    EvalCase(
        id="multi_step_task",
        title="多步任务：创建两个文件并验证",
        prompt=(
            "请完成两件事："
            "1) 创建文件 step1.txt 内容 \"done1\"；"
            "2) 创建文件 step2.txt 内容 \"done2\"。"
            "完成后用一句话确认两件事都办妥了。"
        ),
        setup=lambda ws: None,
        assertions=[
            make_file_exists("step1.txt"),
            make_file_exists("step2.txt"),
            make_file_contains("step1.txt", "done1"),
            make_file_contains("step2.txt", "done2"),
        ],
        tags=["multi_step"],
    ),
    # 19. update_plan
    EvalCase(
        id="update_plan_basic",
        title="调用 update_plan 建计划",
        prompt=(
            "请用 update_plan 工具建立一个 3 步计划："
            "step1=创建 a.txt 内容 hello；step2=创建 b.txt 内容 world；step3=完成。"
            "建好计划后告诉我计划里有几步。"
        ),
        setup=lambda ws: None,
        assertions=[
            make_reply_any(["3", "三", "three", "Three"]),
        ],
        tags=["plan"],
    ),
    # 20. 联网搜索（标记 network=True，--skip-network 可跳过）
    EvalCase(
        id="web_search_basic",
        title="联网搜索一个事实",
        prompt="用 web_search 查 \"Python 3.12 发布\"，告诉我结果里有没有提到 Python 字样。",
        setup=lambda ws: None,
        assertions=[
            make_reply_contains("Python"),
        ],
        network=True,
        tags=["web"],
    ),
]
