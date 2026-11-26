#!/bin/bash
# 啟動 KIF2C 後端 API（從 backend/.env 讀設定，含 GH_TOKEN）。
# 用法: bash backend/run.sh
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -f .env ]; then
  echo "缺 backend/.env —— 請 cp .env.example .env 後填入 GH_TOKEN 等。"; exit 1
fi
set -a; . ./.env; set +a

[ -x .venv/bin/python ] || { echo "缺 venv，請先: uv venv .venv --python 3.12 && uv pip install --python .venv/bin/python -r requirements.txt"; exit 1; }

echo "啟動後端 :${PORT:-8000}（GH_TOKEN 已載入：$([ -n "${GH_TOKEN:-}" ] && echo yes || echo NO）"
exec .venv/bin/python api_server.py
