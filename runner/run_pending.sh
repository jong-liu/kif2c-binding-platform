#!/bin/bash
# 處理 jobs/ 中所有「尚未有結果」的 job（self-hosted runner 與本機測試共用）。
# 單 GPU → 循序處理。已有 results/<id>/ 的 job 會跳過（冪等）。
# 單一 job 失敗不中止整批：記錄失敗結果（避免卡佇列一直重試），繼續下一個。
#
# 逐條增量 commit（KIF2C_COMMIT_EACH=1 時）：每跑完一條就 commit+push，
# 讓前端即時看到結果，且中途被重 checkout 也不會清掉已入庫的結果、不用重算。
# 本機手動測試不設此變數 → 不 commit/push。
set -uo pipefail
cd "$(dirname "$0")/.."

VENV="${KIF2C_VENV:-$HOME/.local/share/kif2c-venv}"
PY=python3
[ -x "$VENV/bin/python" ] && PY="$VENV/bin/python"
[ -x runner/.venv/bin/python ] && PY=runner/.venv/bin/python   # 本機開發優先

BRANCH="${GITHUB_REF_NAME:-main}"
COMMIT_EACH="${KIF2C_COMMIT_EACH:-0}"

# 把單一 job 的結果 commit + push（帶 rebase 重試）。只在 COMMIT_EACH=1 時動作。
commit_push() {   # $1=job id  $2=狀態描述(ok/failed)
  [ "$COMMIT_EACH" = "1" ] || return 0
  git config user.name  >/dev/null 2>&1 || git config user.name  "kif2c-runner[bot]"
  git config user.email >/dev/null 2>&1 || git config user.email "runner@users.noreply.github.com"
  git add "results/$1" 2>/dev/null || true
  git diff --cached --quiet && return 0          # 無變動
  git commit -q -m "results: $1 ($2)" || return 0
  for i in 1 2 3; do
    if git pull --rebase --autostash origin "$BRANCH" && git push origin "HEAD:$BRANCH"; then
      echo "  ↳ 已推送 $1"
      return 0
    fi
    echo "  ↳ 回推衝突，重試 $i"; sleep 3
  done
  echo "  ↳ ⚠️ $1 推送失敗（結果已 commit 於本地，待收尾步驟補推）"
}

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
    commit_push "$id" "ok"
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
    commit_push "$id" "failed"
  fi
  ran=$((ran + 1))
done
echo "— 本輪處理 $ran 個 job —"
[ -n "${GITHUB_ENV:-}" ] && echo "ran=$ran" >> "$GITHUB_ENV" || true
