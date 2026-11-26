#!/bin/bash
# 處理 jobs/ 中所有「尚未有結果」的 job（self-hosted runner 與本機測試共用）。
# 單 GPU → 循序處理。已有 results/<id>/ 的 job 會跳過（冪等）。
# 單一 job 失敗不中止整批：記錄失敗結果（避免卡佇列一直重試），繼續下一個。
set -uo pipefail
cd "$(dirname "$0")/.."

VENV="${KIF2C_VENV:-$HOME/.local/share/kif2c-venv}"
PY=python3
[ -x "$VENV/bin/python" ] && PY="$VENV/bin/python"
[ -x runner/.venv/bin/python ] && PY=runner/.venv/bin/python   # 本機開發優先

shopt -s nullglob
ran=0
for spec in jobs/*.json; do
  id=$(basename "$spec" .json)
  if [ -d "results/$id" ]; then
    echo "✓ $id 已有結果，跳過"
    continue
  fi
  echo "▶ 執行 $id"
  mkdir -p "results/$id"
  if "$PY" runner/run_prediction.py --spec "$spec" --out "results/$id" 2> "results/$id/error.log"; then
    rm -f "results/$id/error.log"
  else
    # 失敗：寫一個 status=failed 的 scores.json，使其視為「已處理」不再重試
    msg=$(tail -c 400 "results/$id/error.log" 2>/dev/null | tr '\n' ' ' | tr -d '"\\')
    "$PY" - "results/$id/scores.json" "$spec" "$msg" <<'PY'
import json, sys
out, spec, msg = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    engine = json.load(open(spec)).get("engine", "?")
except Exception:
    engine = "?"
json.dump({"engine": engine, "status": "failed", "error": msg[-300:]},
          open(out, "w"), ensure_ascii=False, indent=2)
PY
    echo "✗ $id 失敗（已記錄 status=failed，不再重試）"
  fi
  ran=$((ran + 1))
done
echo "— 本輪處理 $ran 個 job —"
[ -n "${GITHUB_ENV:-}" ] && echo "ran=$ran" >> "$GITHUB_ENV" || true
