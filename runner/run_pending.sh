#!/bin/bash
# 處理 jobs/ 中所有「尚未有結果」的 job（self-hosted runner 與本機測試共用同一份邏輯）。
# 單 GPU → 循序處理。已有 results/<id>/ 的 job 會跳過（冪等）。
set -euo pipefail
cd "$(dirname "$0")/.."   # 專案根目錄

# 持久 venv（在 repo 外，避免 actions/checkout 清掉）。可用 KIF2C_VENV 覆寫。
VENV="${KIF2C_VENV:-$HOME/.local/share/kif2c-venv}"
PY=python3
[ -x "$VENV/bin/python" ] && PY="$VENV/bin/python"
[ -x runner/.venv/bin/python ] && PY=runner/.venv/bin/python   # 本機開發若有本地 venv 優先

shopt -s nullglob
ran=0
for spec in jobs/*.json; do
  id=$(basename "$spec" .json)
  if [ -d "results/$id" ]; then
    echo "✓ $id 已有結果，跳過"
    continue
  fi
  echo "▶ 執行 $id"
  "$PY" runner/run_prediction.py --spec "$spec" --out "results/$id"
  ran=$((ran + 1))
done
echo "— 本輪處理 $ran 個 job —"
# 在 GitHub Actions 中把數量輸出給後續步驟
[ -n "${GITHUB_ENV:-}" ] && echo "ran=$ran" >> "$GITHUB_ENV" || true
