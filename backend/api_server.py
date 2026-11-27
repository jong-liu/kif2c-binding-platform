"""
KIF2C Binding Platform — Auth + Job API Server
（帳密驗證架構參考 jong-liu/PL-dock-runner 的 pyrx-web-backend）

- POST /api/login            → {username, password} → {token, username, role}
- POST /api/register         → 待管理員核准
- GET  /api/admin/users      → (admin) 列出使用者
- POST /api/admin/users/<u>/approve|role|delete → (admin) 管理
- POST /api/jobs             → (auth) 送出預測：後端用 GH_TOKEN commit jobs/<id>.json
                               觸發 predict.yml → self-hosted runner 跑 Chai-1
- GET  /api/jobs             → (auth) 列出自己的 job（admin 看全部）
- GET  /api/jobs/<id>        → (auth) 查 job 狀態 + 分數（讀 public repo results/）
- GET  /api/health           → {status: ok}

啟動：
  GH_TOKEN=ghp_xxx JWT_SECRET=xxx python backend/api_server.py
密碼只在後端驗證，前端（GitHub Pages）永遠不持有 GH_TOKEN。
"""
import base64
import hashlib
import json
import os
import re
import secrets
import threading
import time
from functools import wraps

from flask import Flask, jsonify, request
from flask_cors import CORS
import jwt
import requests as req

app = Flask(__name__)
CORS(app,
     origins=[
         "https://jong-liu.github.io",
         "http://localhost", "http://127.0.0.1",
         "http://localhost:8777", "http://127.0.0.1:8777",
     ],
     allow_headers=["Authorization", "Content-Type", "ngrok-skip-browser-warning"],
     methods=["GET", "POST", "DELETE", "OPTIONS"])

# ── Config ─────────────────────────────────────────────
JWT_SECRET = os.environ.get("JWT_SECRET", "kif2c-change-this-secret")
GH_TOKEN   = os.environ.get("GH_TOKEN", "")
GH_OWNER   = os.environ.get("GH_OWNER", "jong-liu")
GH_REPO    = os.environ.get("GH_REPO", "kif2c-binding-platform")
GH_BRANCH  = "main"

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
DATA_DIR   = os.path.join(BASE_DIR, "data")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
JOBS_FILE  = os.path.join(DATA_DIR, "jobs.json")
os.makedirs(DATA_DIR, exist_ok=True)

MAX_TOKENS = 600  # 12GB VRAM 粗略上限（蛋白+peptide 殘基數）


# ── Password helpers（salted SHA-256）──────────────────
def _hash_pw(pw: str) -> str:
    salt = secrets.token_hex(16)
    return f"{salt}:{hashlib.sha256((salt + pw).encode()).hexdigest()}"

def _check_pw(user_data, provided: str) -> bool:
    stored = user_data["password"] if isinstance(user_data, dict) else user_data
    try:
        salt, h = stored.split(":", 1)
        return hashlib.sha256((salt + provided).encode()).hexdigest() == h
    except Exception:
        return False


# ── User store（預設 admin / demo）─────────────────────
def _save_users(users: dict):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)

def load_users() -> dict:
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE) as f:
            return json.load(f)
    # 預設密碼只從環境變數讀，絕不寫死在（公開的）原始碼。
    # 未設定則隨機產生並印出一次，避免 repo 洩漏可登入的帳密。
    admin_pw = os.environ.get("ADMIN_PASSWORD") or ("admin-" + secrets.token_urlsafe(9))
    demo_pw  = os.environ.get("DEMO_PASSWORD")  or ("demo-" + secrets.token_urlsafe(9))
    if not os.environ.get("ADMIN_PASSWORD"):
        print(f"[init] 產生隨機 admin 密碼：{admin_pw}（請記下；或改用 ADMIN_PASSWORD 環境變數）")
    if not os.environ.get("DEMO_PASSWORD"):
        print(f"[init] 產生隨機 demo 密碼：{demo_pw}")
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    defaults = {
        "admin": {"password": _hash_pw(admin_pw), "email": "nthubioinfo@gmail.com",
                  "role": "admin", "status": "active", "created_at": now},
        "demo":  {"password": _hash_pw(demo_pw),  "email": "nthubioinfo@gmail.com",
                  "role": "user",  "status": "active", "created_at": now},
    }
    _save_users(defaults)
    return defaults


# ── Job store ──────────────────────────────────────────
_jobs_lock = threading.Lock()

def load_jobs() -> dict:
    if os.path.exists(JOBS_FILE):
        with open(JOBS_FILE) as f:
            return json.load(f)
    return {}

def save_jobs(jobs: dict):
    with open(JOBS_FILE, "w") as f:
        json.dump(jobs, f, indent=2)


# ── GitHub helpers ─────────────────────────────────────
def _gh_headers() -> dict:
    return {"Authorization": f"token {GH_TOKEN}",
            "Accept": "application/vnd.github+json"}

def _gh_put_job(job_id: str, spec: dict):
    """用 Contents API 建 jobs/<id>.json → push 觸發 predict.yml。"""
    url = f"https://api.github.com/repos/{GH_OWNER}/{GH_REPO}/contents/jobs/{job_id}.json"
    content = base64.b64encode(json.dumps(spec, indent=2).encode()).decode()
    r = req.put(url, headers=_gh_headers(),
                json={"message": f"job: submit {job_id} ({spec.get('engine')})",
                      "content": content, "branch": GH_BRANCH})
    return r

def _gh_get_json(path: str):
    """讀 public repo 的檔（如 results/<id>/scores.json）。"""
    url = f"https://raw.githubusercontent.com/{GH_OWNER}/{GH_REPO}/{GH_BRANCH}/{path}"
    r = req.get(url)
    return r.json() if r.status_code == 200 else None

def _gh_contents(path: str):
    """GET Contents API：檔案回 dict（含 sha），目錄回 list。找不到回 None。"""
    url = f"https://api.github.com/repos/{GH_OWNER}/{GH_REPO}/contents/{path}?ref={GH_BRANCH}"
    r = req.get(url, headers=_gh_headers())
    return r.json() if r.status_code == 200 else None

def _gh_delete_file(path: str, sha: str, msg: str):
    url = f"https://api.github.com/repos/{GH_OWNER}/{GH_REPO}/contents/{path}"
    return req.delete(url, headers=_gh_headers(),
                      json={"message": msg, "sha": sha, "branch": GH_BRANCH})

def _gh_delete_job_files(job_id: str) -> int:
    """best-effort 刪 jobs/<id>.json 與 results/<id>/* 整個目錄。回傳刪除檔數。"""
    deleted = 0
    listing = _gh_contents(f"results/{job_id}")
    if isinstance(listing, list):
        for item in listing:
            if item.get("type") == "file" and item.get("sha"):
                if _gh_delete_file(item["path"], item["sha"],
                                   f"cleanup: delete {item['path']}").status_code == 200:
                    deleted += 1
    jobf = _gh_contents(f"jobs/{job_id}.json")
    if isinstance(jobf, dict) and jobf.get("sha"):
        if _gh_delete_file(f"jobs/{job_id}.json", jobf["sha"],
                           f"cleanup: delete job {job_id}").status_code == 200:
            deleted += 1
    return deleted


def _job_status(scores) -> str:
    """無 scores=running；scores.status==failed=failed；否則 succeeded。"""
    if not scores:
        return "running"
    return "failed" if scores.get("status") == "failed" else "succeeded"


# predict.yml 的步驟名 → 友善中文階段
_STEP_LABELS = {
    "Set up job": "準備工作環境",
    "Checkout": "取得程式碼",
    "Ensure Chai-1 env (uv, 持久 venv)": "準備運算環境",
    "Run pending predictions": "運算預測中（引擎推論）",
    "Commit results": "回寫結果",
    "Complete job": "收尾中",
}

def _epoch(ts: str):
    import calendar
    try:
        return calendar.timegm(time.strptime(ts, "%Y-%m-%dT%H:%M:%SZ"))
    except Exception:
        return None

def _gh_job_progress(job_id: str, created_at: str) -> dict:
    """查 GitHub Actions，回傳該 job 對應 workflow run 的即時進度階段。"""
    now = int(time.time())
    e0 = _epoch(created_at) if created_at else None
    prog = {"stage": "啟動中…", "run_status": "queued", "run_url": None,
            "step_index": None, "total_steps": None,
            "elapsed_sec": (now - e0) if e0 else None}
    if not GH_TOKEN:
        return prog
    try:
        url = (f"https://api.github.com/repos/{GH_OWNER}/{GH_REPO}/actions/"
               f"workflows/predict.yml/runs?per_page=20&branch={GH_BRANCH}")
        runs = req.get(url, headers=_gh_headers(), timeout=8).json().get("workflow_runs", [])
        run = next((r for r in runs
                    if job_id in ((r.get("head_commit") or {}).get("message") or "")), None)
        if not run:
            prog["stage"] = "排隊中（workflow 啟動中）"
            return prog
        prog["run_url"] = run.get("html_url")
        prog["run_status"] = run.get("status")
        if run.get("status") == "queued":
            prog["stage"] = "排隊中（等待 runner 空出）"
            return prog
        jurl = f"https://api.github.com/repos/{GH_OWNER}/{GH_REPO}/actions/runs/{run['id']}/jobs"
        jlist = req.get(jurl, headers=_gh_headers(), timeout=8).json().get("jobs", [])
        if jlist:
            steps = jlist[0].get("steps", [])
            prog["total_steps"] = len(steps)
            cur = next((s for s in steps if s.get("status") == "in_progress"), None)
            if cur:
                prog["stage"] = _STEP_LABELS.get(cur["name"], cur["name"])
                prog["step_index"] = cur.get("number")
                st = cur.get("started_at")
                if st and _epoch(st):
                    prog["step_elapsed_sec"] = now - _epoch(st)
            elif run.get("status") == "completed":
                prog["stage"] = "收尾中（回寫結果）"
            else:
                prog["stage"] = "執行中…"
    except Exception as e:
        print(f"[progress] {job_id}: {e}")
    return prog


# ── Auth decorator ─────────────────────────────────────
def auth_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"error": "Unauthorized"}), 401
        try:
            payload = jwt.decode(auth[7:], JWT_SECRET, algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expired — please log in again"}), 401
        except Exception:
            return jsonify({"error": "Invalid token"}), 401
        return fn(payload, *args, **kwargs)
    return wrapper

def admin_required(fn):
    @wraps(fn)
    @auth_required
    def wrapper(user, *args, **kwargs):
        if user.get("role") != "admin":
            return jsonify({"error": "Admin only"}), 403
        return fn(user, *args, **kwargs)
    return wrapper


# ── Endpoints: health / auth ───────────────────────────
@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "version": "1.0", "gh_configured": bool(GH_TOKEN)})


@app.route("/api/login", methods=["POST"])
def login():
    data = request.json or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")
    users = load_users()
    if username not in users or not _check_pw(users[username], password):
        return jsonify({"error": "Invalid username or password"}), 401
    udata = users[username]
    if udata.get("status", "active") != "active":
        return jsonify({"error": "Account pending admin approval"}), 403
    role = udata.get("role", "user")
    token = jwt.encode({"sub": username, "role": role, "exp": int(time.time()) + 3600 * 8},
                       JWT_SECRET, algorithm="HS256")
    return jsonify({"token": token, "username": username, "role": role})


@app.route("/api/register", methods=["POST"])
def register():
    data = request.json or {}
    username = data.get("username", "").strip().lower()
    password = data.get("password", "")
    email = data.get("email", "").strip()
    if not username or not password or not email:
        return jsonify({"error": "username, password and email are required"}), 400
    if not re.match(r'^[a-zA-Z0-9_]{3,20}$', username):
        return jsonify({"error": "Username: 3–20 alphanumeric/underscore"}), 400
    if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
        return jsonify({"error": "Invalid email"}), 400
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400
    users = load_users()
    if username in users:
        return jsonify({"error": "Username already taken"}), 409
    users[username] = {"password": _hash_pw(password), "email": email, "role": "user",
                       "status": "pending",
                       "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    _save_users(users)
    return jsonify({"message": "Registration submitted. Waiting for admin approval."})


# ── Endpoints: admin ───────────────────────────────────
@app.route("/api/admin/users", methods=["GET"])
@admin_required
def admin_list_users(user):
    users = load_users()
    out = [{"username": u, "email": d.get("email"), "role": d.get("role"),
            "status": d.get("status"), "created_at": d.get("created_at")}
           for u, d in users.items()]
    return jsonify({"users": out})

@app.route("/api/admin/users/<uname>/approve", methods=["POST"])
@admin_required
def admin_approve(user, uname):
    users = load_users()
    if uname not in users:
        return jsonify({"error": "No such user"}), 404
    users[uname]["status"] = "active"
    _save_users(users)
    return jsonify({"message": f"{uname} approved"})

@app.route("/api/admin/users/<uname>", methods=["DELETE"])
@admin_required
def admin_delete(user, uname):
    if uname == "admin":
        return jsonify({"error": "Cannot delete admin"}), 400
    users = load_users()
    if uname in users:
        del users[uname]
        _save_users(users)
    return jsonify({"message": f"{uname} deleted"})


# ── Endpoints: jobs ────────────────────────────────────
@app.route("/api/jobs", methods=["POST"])
@auth_required
def submit_job(user):
    if not GH_TOKEN:
        return jsonify({"error": "Server not configured (GH_TOKEN missing)"}), 500
    data = request.json or {}
    protein = (data.get("protein") or "").strip()
    peptide = (data.get("peptide") or "").strip()
    constraint = (data.get("constraint") or "").strip()
    label = (data.get("label") or "").strip()[:40]  # peptide 名稱（批次 CSV 用）
    engine = data.get("engine", "chai-1")
    if not protein or not peptide:
        return jsonify({"error": "protein 與 peptide 序列必填"}), 400
    est = len(protein) + len(peptide)
    if est > MAX_TOKENS:
        return jsonify({"error": f"系統過大（~{est} residues），12GB 可能 OOM，上限約 {MAX_TOKENS}"}), 400
    # 驗證結合位點約束的殘基序號不超出 protein（Chain A）長度
    con_nums = [int(n) for n in re.findall(r"\d+", constraint)]
    if con_nums and max(con_nums) > len(protein):
        return jsonify({"error": f"約束殘基最大 {max(con_nums)} 超出 protein 長度 {len(protein)}"}), 400

    job_id = f"job-{int(time.time() * 1000)}"
    spec = {
        "id": job_id,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "protein": {"chain": "A", "source": "sequence", "sequence": protein},
        "peptide": {"chain": "B", "sequence": peptide},
        "label": label,
        "constraint": constraint,
        "engine": engine,
        "seed": int(data.get("seed", 42)),
        "num_trunk_recycles": int(data.get("num_trunk_recycles", 2)),
        "num_diffn_timesteps": int(data.get("num_diffn_timesteps", 120)),
        "use_esm": bool(data.get("use_esm", True)),
        "est_tokens": est,
        "submitted_by": user["sub"],
        "status": "queued",
    }
    r = _gh_put_job(job_id, spec)
    if r.status_code not in (200, 201):
        return jsonify({"error": "Failed to submit job to GitHub", "detail": r.text}), 500
    with _jobs_lock:
        jobs = load_jobs()
        jobs[job_id] = {"user": user["sub"], "engine": engine, "constraint": constraint,
                        "label": label, "created_at": spec["created_at"], "est_tokens": est}
        save_jobs(jobs)
    return jsonify({"job_id": job_id, "status": "queued", "est_tokens": est})


@app.route("/api/jobs", methods=["GET"])
@auth_required
def list_jobs(user):
    jobs = load_jobs()
    is_admin = user.get("role") == "admin"
    out = []
    for jid, rec in sorted(jobs.items(), reverse=True):
        if not is_admin and rec.get("user") != user["sub"]:
            continue
        scores = _gh_get_json(f"results/{jid}/scores.json")
        out.append({"job_id": jid, "user": rec.get("user"), "engine": rec.get("engine"),
                    "label": rec.get("label"),
                    "constraint": rec.get("constraint"), "created_at": rec.get("created_at"),
                    "status": _job_status(scores),
                    "error": scores.get("error") if scores and scores.get("status") == "failed" else None,
                    "iptm": scores.get("iptm") if scores else None,
                    "plddt": scores.get("plddt") if scores else None,
                    "contact_satisfied": scores.get("contact_satisfied") if scores else None})
    return jsonify({"jobs": out})


@app.route("/api/jobs/<job_id>", methods=["GET"])
@auth_required
def get_job(user, job_id):
    jobs = load_jobs()
    rec = jobs.get(job_id)
    if not rec:
        return jsonify({"error": "No such job"}), 404
    if user.get("role") != "admin" and rec.get("user") != user["sub"]:
        return jsonify({"error": "Forbidden"}), 403
    scores = _gh_get_json(f"results/{job_id}/scores.json")
    status = _job_status(scores)
    ok = scores and scores.get("status") != "failed"
    pdb_url = (f"https://raw.githubusercontent.com/{GH_OWNER}/{GH_REPO}/{GH_BRANCH}/"
               f"results/{job_id}/complex.pdb")
    resp = {"job_id": job_id, "status": status,
            "scores": scores, "pdb_url": pdb_url if ok else None}
    if status == "running":   # 只在運行中才查 Actions 進度（避免多餘 API 呼叫）
        resp["progress"] = _gh_job_progress(job_id, rec.get("created_at"))
    return jsonify(resp)


@app.route("/api/jobs/<job_id>", methods=["DELETE"])
@auth_required
def delete_job(user, job_id):
    """刪除 job：擁有者本人或 admin 可刪。移除後端記錄 + GitHub 上的 job/結果檔。"""
    with _jobs_lock:
        jobs = load_jobs()
        rec = jobs.get(job_id)
        if not rec:
            return jsonify({"error": "No such job"}), 404
        if user.get("role") != "admin" and rec.get("user") != user["sub"]:
            return jsonify({"error": "Forbidden"}), 403
        del jobs[job_id]          # 先移除後端記錄 → 使用者列表立即消失
        save_jobs(jobs)
    files_removed = 0             # 再 best-effort 清掉 GitHub 上的檔案
    if GH_TOKEN:
        try:
            files_removed = _gh_delete_job_files(job_id)
        except Exception as e:
            print(f"[delete_job] GitHub 清檔失敗 {job_id}: {e}")
    return jsonify({"message": f"job {job_id} deleted", "files_removed": files_removed})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"KIF2C API on :{port}  (gh_configured={bool(GH_TOKEN)})")
    app.run(host="0.0.0.0", port=port)
