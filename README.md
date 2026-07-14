---
title: Tangyuan Demo
emoji: 🥟
colorFrom: yellow
colorTo: green
sdk: docker
pinned: false
app_port: 7860
---

# 汤圆 Tangyuan

**终端里的通用 Agent** — 独立实现的多工具闭环助手（读改文件、跑命令、搜网页、任务规划、子代理、MCP）。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Live Demo](https://img.shields.io/badge/🤗%20Live%20Demo-Hugging%20Face-ffcc00)](https://huggingface.co/spaces/lichenyu666/tangyuan-demo)

> 简历访客？直接打开 **[在线 Demo](https://huggingface.co/spaces/lichenyu666/tangyuan-demo)** 和汤圆聊聊这个项目。

## 它能做什么

| 能力 | 说明 |
|------|------|
| 任务规划 | `update_plan` + Stop Gate，复杂多步不半途而废 |
| 子代理 / Team | `dispatch_subagent`、队友 inbox / broadcast |
| MCP | 默认内置 time server；可接更多 stdio MCP |
| 文件与命令 | 读/写/搜文件、`apply_patch`、受控 `run_shell` |
| 网页 | `web_search` / `fetch_url` |
| Skills | 渐进披露：摘要进提示，匹配后再 `load_skill` |
| 长期记忆 | MEMORY + 日记 + history / tokens 计量 |
| Trace | `.tangyuan/traces/*.jsonl` 可复盘 |

## 快速开始

需要 Python ≥ 3.10，以及任意 **OpenAI 兼容** API（DeepSeek / 通义 / OpenAI / 本地网关）。

```bash
git clone https://github.com/lichenyu666/tangyuan.git
cd tangyuan
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .

cp .env.example .env
# 编辑 .env，填入 TANGYUAN_API_KEY / TANGYUAN_BASE_URL / TANGYUAN_MODEL

tangyuan
```

单次任务：

```bash
tangyuan run "总结当前仓库" -w .
```

可选：把 venv 里的可执行文件链到 PATH，任意目录直接敲 `tangyuan` / `ty`。

## 配置

见 [`.env.example`](.env.example)。密钥只放 `.env` 或 `~/.tangyuan/.env`，**不要提交到 Git**。

```bash
# 最小示例
TANGYUAN_API_KEY=sk-xxx
TANGYUAN_BASE_URL=https://api.deepseek.com
TANGYUAN_MODEL=deepseek-chat
```

MCP 可选依赖：

```bash
pip install -e '.[mcp]'
```

在线 Demo（Gradio）本地跑：

```bash
pip install -e '.[web]'
python -m tangyuan.web.app
```

### 部署到 Hugging Face Spaces

GitHub Pages 无法跑 Python Agent。公开 Demo：
[huggingface.co/spaces/lichenyu666/tangyuan-demo](https://huggingface.co/spaces/lichenyu666/tangyuan-demo)

一次性配置：

1. 登录 [Hugging Face](https://huggingface.co/join)，在 [Access Tokens](https://huggingface.co/settings/tokens) 创建 **Write** token  
2. 本机已有 `.env`（含 `TANGYUAN_API_KEY`）时执行：

```bash
export HF_TOKEN=hf_xxx
pip install huggingface_hub
python scripts/setup_hf_space.py
```

脚本会创建 Space、上传 Docker 构建文件，并把 API Key 写入 Space Secrets（不打印密钥）。  
也可在 GitHub → Settings → Secrets 添加 `HF_TOKEN`，用 workflow `Sync Hugging Face Space` 同步代码。

## 工程分层

```text
tangyuan/
  agent/       # 工具循环 · 任务计划 · 子代理
  hooks/       # before/after tool · Stop Gate
  mcp/         # stdio MCP Client
  memory/      # MEMORY / 日记 / history / tokens
  skills/      # 发现与渐进披露
  tools/       # fs · shell · web · git · search · …
  prompts/     # SOUL / system / compact / distill
  ui/          # Rich 终端主题
  web/         # 公开 Demo（Gradio，工具已锁死）
  cli.py
```

## 安全

- API Key 仅服务端 / 本机 `.env`（已 gitignore）
- 交互模式默认对 shell、写文件二次确认（`-y` 可关）
- 危险 shell（如 `rm -rf /`、`curl|sh`）即使 `-y` 也会拒绝
- 写文件默认限制在 workspace 内
- **在线 Demo** 禁用 shell、写盘、子代理、Team、MCP，并限流

## 和 Claude Code 的定位差

| | Claude Code | 汤圆 |
|--|-------------|------|
| 定位 | 深度 IDE / 生态 | 轻量自研终端 Agent |
| MCP | 成熟市场 | 已接 Client，生态仍在长 |
| 交互 | IDE + diff UX | 终端文本为主 |
| 安全 | 成熟沙箱 | 确认 + 路径约束 + Demo 白名单 |

## 路线图

- [x] Skills 渐进披露 · 分层记忆 · `apply_patch`
- [x] 任务计划 · 子代理 · Agent Team · MCP · Hooks
- [x] 公开仓库 + Gradio 在线 Demo
- [ ] 评测集与成功率统计
- [ ] 更强沙箱与权限模型

## License

[MIT](LICENSE) © li_chenyu
