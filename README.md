# 汤圆 Tangyuan

终端里的通用 Agent（李晨雨独立实现：终端对话框 + 多工具闭环）。

## 工程分层

```text
tangyuan/
  agent/                 # 脑子：工具循环 + 任务计划 + 子代理
    plan.py              # 结构化任务板 TaskPlan
    subagent.py          # 独立上下文派遣
  hooks/                 # 生命周期：before/after tool、Stop Gate
  mcp/                   # stdio MCP Client
  memory/                # 记忆：MEMORY / 日记 / history / tokens
  skills/
    loader.py            # 技能发现与渐进披露
    catalog/*/SKILL.md   # 内置剧本
  tools/
    register_*.py        # fs / shell / web / memory / plan / subagent / mcp
    fs|shell|web|…       # 工具实现
  prompts/
    SOUL.md              # 人设
    system.md            # 工作准则
    workspace.md         # 工作位置
    compact.md           # 上下文压缩
    distill.md           # 项目蒸馏
    assemble.py          # 全量 system prompt 组装
  cli.py / config.py / trace.py
skills/                  # 可选：工作区覆盖剧本（见其中 README）
```

## 现在能做什么（v0.3）

| 能力 | 工具 |
|------|------|
| 任务规划（复杂多步） | `update_plan`；结束 Stop Gate 拦残单；办妥清空 |
| 子代理 | `dispatch_subagent`（explore / research / coder） |
| Agent Team | `spawn_teammate` / `send_message` / `read_inbox` / `broadcast`（`/team` `/inbox`） |
| MCP | 默认内置 `time` server（`mcp_time_*`）；可改 `.tangyuan/mcp_servers.json` |
| Hooks | 输出截断、写操作审计、计划收工门禁 |
| 读/写/搜文件、跑命令 | `list_dir` `read_file` `write_file` `apply_patch` `search_text` `run_shell` |
| 搜网页 / 抓网页 | `web_search` `fetch_url` |
| 打开链接、文件、App | `open_path` `open_app` |
| 移到废纸篓（需确认） | `move_to_trash` |
| 生成简单 PPT | `create_pptx` |
| 拖文件 / `@路径` 附件 | 自动读入对话 |
| Skills（修报错 / 讲仓库 / 做 PPT） | **渐进披露**：系统提示只放摘要，匹配后 `load_skill`；也可用 `/skill <id>` 强制 |
| 长期记忆（跨对话） | **工程化**：`MEMORY.md` + 日记 + `history.jsonl` + `tokens.jsonl`；会话压缩与项目蒸馏 |
| 多轮对话记忆 | 同一会话连续聊（`/clear` 只清本轮，不清长期记忆） |
| Trace 复盘 | `.tangyuan/traces/*.jsonl` |

## 快速开始

首次安装（只需一次）：

```bash
cd /Users/li_chenyu/code/tangyuan
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env   # 填 API Key（勿提交 GitHub；任意目录启动会自动读到）

# 装到全局命令（任意目录可直接敲 tangyuan）
ln -sf "$(pwd)/.venv/bin/tangyuan" /opt/homebrew/bin/tangyuan
ln -sf "$(pwd)/.venv/bin/ty" /opt/homebrew/bin/ty
```

之后任意目录启动：

```bash
tangyuan
```

然后可以直接说：

```text
帮我搜一下 LangGraph 官方文档，并打开链接
打开计算器
根据 README 做个 3 页 PPT，保存到 output/intro.pptx
@README.md 用中文总结这个项目
```

单次任务：

```bash
tangyuan run "总结当前仓库" -w .
```

## 和 Claude Code 差在哪（避免预期错位）

| Claude Code | 汤圆 v0.2 |
|-------------|-----------|
| 深度 IDE/权限/生态 | 轻量自研 |
| 复杂 MCP 市场 | 尚未接 MCP（路线图） |
| 强 IDE 集成 / diff UX | 终端文本为主 |
| 成熟安全沙箱 | 基础确认 + 路径约束 |
| 拖拽体验打磨 | 终端粘贴路径 / `@文件` |

## 安全

- API Key 只放 `.env` / `~/.tangyuan/.env`（已 gitignore）
- `run_shell` / 写文件 / `apply_patch` / 废纸篓：交互模式默认二次确认（`-y` 可关）
- 部分危险 shell（如 `rm -rf /`、`curl|sh`）即使 `-y` 也会直接拒绝
- 写文件默认限制在 workspace 内；读可用用户拖入的绝对路径

## Skills（渐进式披露）

目录：内置 `tangyuan/skills/catalog/<id>/SKILL.md`；工作区可放 `skills/<id>/SKILL.md` 覆盖。

| id | 作用 |
|----|------|
| `fix-error` | 修报错 |
| `explain-repo` | 讲解仓库 |
| `make-pptx` | 生成 PPT |

- **默认自动（渐进披露）**：系统提示只放摘要；匹配意图后模型先 `load_skill` 再按全文执行  
- **手动强制**：`/skill fix-error`（直接注入全文）；取消：`/skill off`  
- 查看：`/skills`

## MCP

启动时若没有配置，会自动在工作区写入 `.tangyuan/mcp_servers.json`，并启用内置 **time** server（`mcp_time_get_current_time` 等）。

也可手动改该文件接入更多 MCP Server。需要 Python≥3.10 与 `pip install 'tangyuan[mcp]'`（本仓库 venv 已装好）。

## 记忆（工程化目录）

全局 `~/.tangyuan/memory/`：

| 文件 | 作用 |
|------|------|
| `MEMORY.md` | 稳定长期记忆（画像/偏好） |
| `YYYY-MM-DD.md` | 按日过程日记 |
| `history.jsonl` | 对话历史事件流 |
| `tokens.jsonl` | Token 用量计量 |

项目 `<workspace>/.tangyuan/memory/MEMORY.md`：本仓库约定（默认不常驻系统提示）。

| 类型 | 新开对话还在吗 | 是否常驻系统提示 |
|------|----------------|------------------|
| 工作记忆 messages | 否 | 是（过长压缩） |
| MEMORY.md | **是** | 短摘要常驻 |
| 日记 / history / tokens | **是** | 否（落盘可查） |
| 项目 MEMORY | **是** | 否，`recall_memory` |

```text
/remember topic:姓名 李晨雨
/remember project 本仓库默认用 DeepSeek
/remember daily 今天把 apply_patch 做完了
/memory
/tokens
```

`/clear` 与 `/exit` 会蒸馏项目级结论；过程也会记入当日日记。

## 路线图

- [x] Skills 自动加载（+ 可手动强制）
- [x] Skills 渐进式披露（`load_skill`）
- [x] 分层记忆 + 会话压缩 + 项目蒸馏
- [x] `apply_patch` 精细改文件
- [x] 结构化任务计划 `update_plan`（未完成项跟踪；Stop Gate 收口）
- [x] 子代理 `dispatch_subagent`
- [x] Agent Team（spawn / inbox / broadcast）
- [x] MCP Client（默认内置 time server）
- [x] Hooks（审计 / 截断 / 计划门禁）
- [ ] 评测集与成功率统计
- [ ] LangGraph 状态机重构

## License

MIT
