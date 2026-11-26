# KIF2C 後端 API（帳密驗證 + 送單）

帳密在後端驗證（salted SHA-256 + JWT），前端（GitHub Pages）不持有任何 token。
架構參考 `jong-liu/PL-dock-runner` 的 pyrx-web-backend。

## 端點

| Method | Path | 說明 |
|--------|------|------|
| POST | `/api/login` | `{username,password}` → `{token,username,role}` |
| POST | `/api/register` | 註冊，待管理員核准 |
| GET | `/api/admin/users` | (admin) 列使用者 |
| POST | `/api/admin/users/<u>/approve` · DELETE `/api/admin/users/<u>` | (admin) 管理 |
| POST | `/api/jobs` | (auth) 送單：後端用 GH_TOKEN commit `jobs/<id>.json` 觸發 predict.yml |
| GET | `/api/jobs` · `/api/jobs/<id>` | (auth) 查自己的 job（admin 看全部） |

## 帳號

- `admin`（管理者）/ `demo`（使用者）。密碼存 `data/users.json`（雜湊，gitignored）。
- 首次建立時的預設密碼由 `ADMIN_PASSWORD` / `DEMO_PASSWORD` 環境變數決定；未設則隨機產生並印出。
- **原始碼不含任何明碼密碼**（repo 公開）。

## 一次性設定

```bash
cd backend
cp .env.example .env            # 填 GH_TOKEN（gh auth token 可印出）、JWT_SECRET
uv venv .venv --python 3.12
uv pip install --python .venv/bin/python -r requirements.txt
bash run.sh                     # 啟動 :8000
```

## 對外暴露（給 Pages 前端連）

ngrok 若已被其他服務佔用，用 cloudflared quick tunnel（免費、免帳號）：

```bash
cloudflared tunnel --url http://localhost:8000 --protocol http2
# 取得 https://xxxx.trycloudflare.com → 填進前端登入框「後端 API」欄，
# 或改 frontend/app.js 的 DEFAULT_API_BASE 後重新部署 Pages。
```

> QUIC(UDP 7844) 常被擋，故加 `--protocol http2`。
> quick tunnel 網址每次重啟會變；要固定網址請設 named tunnel（需 Cloudflare 帳號 + 網域）。

## 長期穩定（開機自啟）

把後端與隧道設成 systemd user service（免 sudo）：`~/.config/systemd/user/`，
`systemctl --user enable --now kif2c-api kif2c-tunnel`。（範本可後續補。）

## 安全

- `data/`（含密碼雜湊）與 `.env`（含 GH_TOKEN）皆 gitignored，永不進 repo。
- GH_TOKEN 只在後端；前端永遠拿不到。
- repo 公開但 predict.yml 只在 push `jobs/**` 時觸發、不吃 fork PR。
