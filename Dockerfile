# syntax=docker/dockerfile:1
FROM python:3.11-slim

WORKDIR /app

# 部分工具链会用到 git（只读 git_*）；保持镜像精简
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md LICENSE .env.example ./
COPY tangyuan ./tangyuan
COPY demo_workspace ./demo_workspace
COPY skills ./skills

RUN pip install --no-cache-dir -e '.[web]'

ENV TANGYUAN_DEMO_WORKSPACE=/app/demo_workspace
ENV TANGYUAN_MAX_STEPS=12
ENV GRADIO_SERVER_NAME=0.0.0.0
ENV GRADIO_SERVER_PORT=7860
# API Key 通过 Space Secrets / 运行时环境注入，切勿写进镜像

EXPOSE 7860
CMD ["python", "-m", "tangyuan.web.app"]
