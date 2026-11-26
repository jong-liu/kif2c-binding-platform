#!/bin/bash
# 取得 cloudflared 當前 quick-tunnel 網址，若與前端 DEFAULT_API_BASE 不同，
# 就用 GitHub API 更新 frontend/app.js 並 push（觸發 pages.yml 重新部署）。
# 由 kif2c-tunnel.service 的 ExecStartPost 在每次隧道啟動時呼叫。
set -uo pipefail

ENVFILE="$HOME/kif2c-binding-platform/backend/.env"
[ -f "$ENVFILE" ] || { echo "no .env"; exit 0; }
set -a; . "$ENVFILE"; set +a
[ -n "${GH_TOKEN:-}" ] || { echo "no GH_TOKEN"; exit 0; }
OWNER="${GH_OWNER:-jong-liu}"; REPO="${GH_REPO:-kif2c-binding-platform}"

# 1) 等 cloudflared 印出網址（最多 ~50s）
URL=""
for _ in $(seq 1 25); do
  URL=$(journalctl --user -u kif2c-tunnel.service --since "-5 min" --no-pager 2>/dev/null \
        | grep -oE "https://[a-z0-9-]+\.trycloudflare\.com" | tail -1)
  [ -n "$URL" ] && break
  sleep 2
done
[ -z "$URL" ] && { echo "tunnel url not found yet"; exit 0; }

API="https://api.github.com/repos/$OWNER/$REPO/contents/frontend/app.js"
AUTH="Authorization: token $GH_TOKEN"
ACC="Accept: application/vnd.github+json"

# 2) 讀目前 app.js
resp=$(curl -s -H "$AUTH" -H "$ACC" "$API")
sha=$(printf '%s' "$resp" | python3 -c "import sys,json;print(json.load(sys.stdin).get('sha',''))")
content=$(printf '%s' "$resp" | python3 -c "import sys,json,base64;print(base64.b64decode(json.load(sys.stdin)['content']).decode(),end='')")
[ -n "$sha" ] || { echo "cannot read app.js"; exit 0; }

cur=$(printf '%s' "$content" | grep -oE 'const DEFAULT_API_BASE = "[^"]*"' | sed -E 's/.*"([^"]*)".*/\1/')
if [ "$cur" = "$URL" ]; then echo "url unchanged: $URL"; exit 0; fi

# 3) 置換該行後用 GitHub API PUT（python 處理置換與 base64/JSON，避免跳脫問題）
python3 - "$content" "$URL" "$sha" "$API" "$GH_TOKEN" <<'PY'
import base64, json, re, sys, urllib.request
content, url, sha, api, tok = sys.argv[1:6]
new = re.sub(r'(const DEFAULT_API_BASE = ")[^"]*(")', r'\g<1>'+url+r'\g<2>', content)
body = json.dumps({"message": f"chore: auto-update tunnel url -> {url}",
                   "content": base64.b64encode(new.encode()).decode(), "sha": sha}).encode()
req = urllib.request.Request(api, data=body, method="PUT",
    headers={"Authorization": f"token {tok}", "Accept": "application/vnd.github+json"})
try:
    urllib.request.urlopen(req, timeout=30)
    print("updated frontend DEFAULT_API_BASE ->", url)
except Exception as e:
    print("update failed:", e)
PY
