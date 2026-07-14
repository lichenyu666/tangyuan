# 汤圆项目概览

汤圆（Tangyuan）是一个从零自研的终端通用 Agent，约 7500 行 Python，兼容任意
OpenAI 风格接口（DeepSeek / 通义 / OpenAI / 本地网关）。它不依赖 LangChain、
LangGraph 等 Agent 框架，而是自行实现工具循环、上下文工程、记忆与安全边界。

## 记忆系统分层

汤圆的记忆分为多层：

- 全局长期记忆：~/.tangyuan/memory/MEMORY.md，保存用户画像与偏好，会常驻系统提示（截断）。
- 按日日记：~/.tangyuan/memory/YYYY-MM-DD.md，记录当天过程。
- 对话历史：history.jsonl，事件流。
- Token 计量：tokens.jsonl，用于成本分析。
- 项目记忆：<workspace>/.tangyuan/memory/MEMORY.md，保存某个仓库的约定与结论，按需召回。

## 上下文工程

长对话会撑爆上下文窗口。汤圆用会话压缩（把旧轮次用 LLM 摘要归档，只保留最近若干轮）
加项目蒸馏（把稳定结论写入项目记忆）来控制上下文长度，而不是简单截断历史。

## 任务规划与 Stop Gate

汤圆用结构化任务板 TaskPlan 推进复杂任务，并用 Stop Gate 门禁：当模型想结束但仍有
未完成计划项时，阻断收工并注入催办（有最大次数保护）。另有 stall 检测在连续多步无进展
时提醒换路径。

## 在线 Demo 的安全约束

公开 Demo 使用只读工具白名单，故意关闭了危险能力：不能执行 shell、不能写文件或打补丁、
不能开子代理 / Agent Team / MCP，并对消息数与请求频率做限流。完整能力需本地安装后使用。
