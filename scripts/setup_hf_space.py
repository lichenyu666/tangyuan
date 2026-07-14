#!/usr/bin/env python3
"""Create / update Hugging Face Space for Tangyuan Demo.

Prerequisites:
  1. Create a Write token at https://huggingface.co/settings/tokens
  2. export HF_TOKEN=hf_...
  3. Ensure .env has TANGYUAN_API_KEY (and optional BASE_URL / MODEL)

Usage (from repo root):
  python scripts/setup_hf_space.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def main() -> int:
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    if not token:
        print("缺少 HF_TOKEN。请先：", file=sys.stderr)
        print("  1) https://huggingface.co/settings/tokens 创建 Write token", file=sys.stderr)
        print("  2) export HF_TOKEN=hf_xxx", file=sys.stderr)
        print("  3) python scripts/setup_hf_space.py", file=sys.stderr)
        return 1

    try:
        from huggingface_hub import HfApi, add_space_secret
    except ImportError:
        print("请先: pip install huggingface_hub", file=sys.stderr)
        return 1

    env = _load_dotenv(ROOT / ".env")
    api_key = os.environ.get("TANGYUAN_API_KEY") or env.get("TANGYUAN_API_KEY", "")
    base_url = (
        os.environ.get("TANGYUAN_BASE_URL")
        or env.get("TANGYUAN_BASE_URL")
        or "https://api.deepseek.com"
    )
    model = (
        os.environ.get("TANGYUAN_MODEL") or env.get("TANGYUAN_MODEL") or "deepseek-chat"
    )

    if not api_key or api_key.startswith("sk-xxx"):
        print("未找到有效的 TANGYUAN_API_KEY（检查 .env）", file=sys.stderr)
        return 1

    api = HfApi(token=token)
    who = api.whoami()
    username = who["name"] if isinstance(who, dict) else str(who)
    print(f"HF user: {username}")

    # Prefer fixed public name used in README badges
    preferred = "lichenyu666/tangyuan-demo"
    repo_id = preferred if username == "lichenyu666" else f"{username}/tangyuan-demo"

    try:
        api.create_repo(
            repo_id=repo_id,
            repo_type="space",
            space_sdk="docker",
            private=False,
            exist_ok=True,
        )
        print(f"Space ready: https://huggingface.co/spaces/{repo_id}")
    except Exception as e:  # noqa: BLE001
        print(f"create_repo failed: {e}", file=sys.stderr)
        return 1

    for rel in (
        "Dockerfile",
        ".dockerignore",
        "pyproject.toml",
        "README.md",
        "LICENSE",
        ".env.example",
    ):
        path = ROOT / rel
        if path.is_file():
            api.upload_file(
                path_or_fileobj=str(path),
                path_in_repo=rel,
                repo_id=repo_id,
                repo_type="space",
            )
            print(f"uploaded {rel}")

    for folder in ("tangyuan", "demo_workspace", "skills"):
        src = ROOT / folder
        if src.is_dir():
            api.upload_folder(
                folder_path=str(src),
                path_in_repo=folder,
                repo_id=repo_id,
                repo_type="space",
                ignore_patterns=["**/__pycache__/**", "**/*.pyc", "**/.DS_Store"],
            )
            print(f"uploaded {folder}/")

    add_space_secret(repo_id, "TANGYUAN_API_KEY", api_key, token=token)
    add_space_secret(repo_id, "TANGYUAN_BASE_URL", base_url, token=token)
    add_space_secret(repo_id, "TANGYUAN_MODEL", model, token=token)
    add_space_secret(repo_id, "TANGYUAN_MAX_STEPS", "12", token=token)
    print("Secrets set (API key not printed).")
    print(f"\nLive Demo: https://huggingface.co/spaces/{repo_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
