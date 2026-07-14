# 本地安装（完整终端版）

```bash
git clone https://github.com/lichenyu666/tangyuan.git
cd tangyuan
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
# 编辑 .env 填入 API Key
tangyuan
```

环境变量说明见仓库根目录 `.env.example`。
