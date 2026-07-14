# Security Policy

## 支持的版本

当前以 GitHub `main` 分支为准（v0.3.x）。

## 报告漏洞

如果你发现可导致任意命令执行、密钥泄露、路径逃逸等问题：

1. **不要**公开提 Issue 贴出利用细节
2. 请发邮件或通过 GitHub Security Advisory 私下告知维护者（账号：[lichenyu666](https://github.com/lichenyu666)）
3. 请说明影响范围与复现步骤

我们会尽快确认并修复。感谢负责任的披露。

## 使用注意

- API Key 只放本地 `.env` / `~/.tangyuan/.env`
- 公网部署时务必限制工具权限（禁用 shell / 写盘等），并做好限流
