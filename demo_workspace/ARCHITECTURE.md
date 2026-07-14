# 汤圆架构速览

```text
tangyuan/
  agent/     # TangyuanAgent：流式补全 + 工具循环 + TaskPlan + 子代理
  hooks/     # before/after tool、Stop Gate（计划未完成不收工）
  mcp/       # stdio MCP Client（Demo 关闭）
  memory/    # MEMORY.md · 日记 · history.jsonl · tokens.jsonl
  skills/    # catalog/*/SKILL.md，渐进披露（load_skill）
  tools/     # fs / shell / web / git / search / plan / …
  prompts/   # SOUL.md · system.md · compact · distill · assemble
  ui/        # Rich 终端主题
  web/       # Gradio 公开 Demo（本进程）
  cli.py     # tangyuan / ty 入口
```

## 核心循环

1. 用户输入 → 拼进 messages
2. 流式调用 LLM（OpenAI 兼容）
3. 若有 tool_calls → 执行工具 → 结果回填 → 继续
4. 无工具调用 → 输出最终回答；若计划未完成则 Stop Gate 催促继续

## 关键安全开关

- CLI：`read_only=True`（`tangyuan plan`）限制写操作
- Demo：`build_demo_tools()` 在只读基础上再卸掉 shell / remember / 子代理等
