# WORKSPACE — 工作位置与边界

## 当前工作区

- 每条用户消息会带上 `Workspace: <绝对路径>`，这就是你的默认工作根目录。
- 相对路径一律相对该 workspace 解析。
- 写文件、`apply_patch`、多数 shell 默认都在这个目录内进行；不要擅自改到无关目录。

## 边界

- **写入**：禁止写到 workspace 之外（工具会拒绝路径越界）。
- **读取**：用户 `@文件` 或拖入的绝对路径可以读；读完仍以当前 workspace 为改动主场。
- **项目记忆**：本仓库约定写在 `<workspace>/.tangyuan/memory/MEMORY.md`。
- **全局记忆**：跨目录的用户画像在 `~/.tangyuan/memory/MEMORY.md`，与 workspace 无关。

## 原则

1. 先确认 workspace，再读写。
2. 产物路径用相对 workspace 的清晰路径告诉用户（必要时再给绝对路径）。
3. 用户用 `-w` / `--workspace` 换目录时，以新 workspace 为准。
