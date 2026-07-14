# 参与汤圆

谢谢你愿意一起改进！

## 开发

```bash
git clone https://github.com/lichenyu666/tangyuan.git
cd tangyuan
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env   # 填入自己的 API Key，勿提交
tangyuan
```

## 提 PR 前

1. 改动尽量小而清晰，说明「为什么」
2. 不要提交 `.env`、密钥、本机绝对路径
3. 能跑通：`tangyuan --help`；若改工具/Agent，请本地对话验证一下

## 提 Issue

- Bug：用 Bug 模板，尽量带复现步骤与环境
- 想法：用 Feature 模板，或开 [Discussions](https://github.com/lichenyu666/tangyuan/discussions)

## 行为准则

友善、具体、对事不对人。恶意利用本工具危害他人系统的讨论不予接受。
