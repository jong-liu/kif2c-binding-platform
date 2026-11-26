/* KIF2C Binding Platform — 前端（後端帳密版）
 * 所有操作經後端 API（經 ngrok/cloudflared 隧道）；前端不持有 GitHub token。
 * 架構參考 jong-liu/PL-dock-runner。
 */
const $ = (id) => document.getElementById(id);
const LS = {
  get: (k) => localStorage.getItem(k) || "",
  set: (k, v) => localStorage.setItem(k, v),
  del: (k) => localStorage.removeItem(k),
};

// 後端 API base：優先 localStorage，其次內建預設（部署時填入隧道網址）
// ⚠️ 這是 cloudflared quick tunnel 的「臨時」網址，後端/隧道重啟就會變。
// 正式用請改成固定的 named tunnel 網址，或在登入框的「後端 API」欄位手動覆寫。
const DEFAULT_API_BASE = "https://tasks-parade-shoot-compute.trycloudflare.com";
function apiBase() { return (LS.get("kif2c_api") || DEFAULT_API_BASE).replace(/\/$/, ""); }
function token() { return LS.get("kif2c_token"); }

let currentPdb = null, currentJob = null;

// ── API helper ─────────────────────────────────────────
async function api(path, opts = {}) {
  const base = apiBase();
  if (!base) throw new Error("尚未設定後端 API 網址");
  const headers = { "Content-Type": "application/json", "ngrok-skip-browser-warning": "true", ...(opts.headers || {}) };
  if (token()) headers["Authorization"] = "Bearer " + token();
  const res = await fetch(base + path, { ...opts, headers });
  if (res.status === 401) { doLogout(); throw new Error("請重新登入"); }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

// ── 登入 / 註冊 / 登出 ──────────────────────────────────
$("apiBase").value = LS.get("kif2c_api");
$("apiBase").onchange = () => LS.set("kif2c_api", $("apiBase").value.trim());

$("toRegister").onclick = () => { $("loginView").hidden = true; $("registerView").hidden = false; };
$("toLogin").onclick = () => { $("registerView").hidden = true; $("loginView").hidden = false; };

$("loginBtn").onclick = async () => {
  $("loginError").textContent = "";
  $("loginBtn").disabled = true; $("loginBtn").textContent = "登入中…";
  try {
    const d = await api("/api/login", {
      method: "POST",
      body: JSON.stringify({ username: $("loginUser").value.trim(), password: $("loginPass").value }),
    });
    LS.set("kif2c_token", d.token); LS.set("kif2c_user", d.username); LS.set("kif2c_role", d.role || "user");
    enterApp();
  } catch (e) { $("loginError").textContent = e.message; }
  finally { $("loginBtn").disabled = false; $("loginBtn").textContent = "登入"; }
};

$("regBtn").onclick = async () => {
  $("regError").textContent = "";
  try {
    const d = await api("/api/register", {
      method: "POST",
      body: JSON.stringify({ username: $("regUser").value.trim(), email: $("regEmail").value.trim(), password: $("regPass").value }),
    });
    $("regError").style.color = "var(--ok)";
    $("regError").textContent = d.message || "已送出，待管理員核准";
  } catch (e) { $("regError").style.color = "var(--err)"; $("regError").textContent = e.message; }
};

function doLogout() {
  LS.del("kif2c_token"); LS.del("kif2c_user"); LS.del("kif2c_role");
  $("app").hidden = true; $("loginOverlay").hidden = false;
  $("loginPass").value = "";
}

function enterApp() {
  $("loginOverlay").hidden = true; $("app").hidden = false;
  const u = LS.get("kif2c_user"), role = LS.get("kif2c_role");
  $("userBadge").innerHTML = `👤 ${u}${role === "admin" ? " <b>[admin]</b>" : ""} · <a href="#" id="logoutLink">登出</a>`;
  $("logoutLink").onclick = (e) => { e.preventDefault(); doLogout(); };
  $("adminPanel").hidden = role !== "admin";
  if (role === "admin") loadUsers();
  refreshJobs();
}

// ── Token 估算 ─────────────────────────────────────────
function estTokens() {
  const t = $("protein").value.replace(/\s/g, "").length + $("peptide").value.replace(/\s/g, "").length;
  $("estTokens").textContent = t ? `約 ${t} residues${t > 600 ? " ⚠️ 12GB 可能 OOM" : ""}` : "";
}
$("protein").oninput = estTokens; $("peptide").oninput = estTokens;

// ── 送單 ───────────────────────────────────────────────
$("submitBtn").onclick = async () => {
  $("submitState").textContent = "送出中…";
  try {
    const d = await api("/api/jobs", {
      method: "POST",
      body: JSON.stringify({
        protein: $("protein").value.replace(/\s/g, ""),
        peptide: $("peptide").value.replace(/\s/g, ""),
        constraint: $("constraint").value.trim(),
        engine: $("engine").value,
      }),
    });
    $("submitState").textContent = `已送出 ${d.job_id} ✓`;
    refreshJobs();
  } catch (e) { $("submitState").textContent = "失敗：" + e.message; }
};

// ── Jobs 列表 ──────────────────────────────────────────
async function refreshJobs() {
  const tb = $("jobTable").querySelector("tbody");
  tb.innerHTML = `<tr><td colspan="6" class="muted">載入中…</td></tr>`;
  try {
    const { jobs } = await api("/api/jobs");
    tb.innerHTML = "";
    if (!jobs.length) { tb.innerHTML = `<tr><td colspan="6" class="muted">尚無 job</td></tr>`; return; }
    for (const j of jobs) {
      const tr = document.createElement("tr");
      const done = j.status === "succeeded";
      tr.innerHTML = `<td>${j.job_id}</td>
        <td><span class="badge ${done ? "succeeded" : "running"}">${j.status}</span></td>
        <td>${j.iptm ?? "—"}</td><td>${j.plddt ?? "—"}</td>
        <td>${j.constraint || "—"}</td>
        <td>${done ? `<button class="small" data-id="${j.job_id}">檢視</button>` : ""}</td>`;
      tb.appendChild(tr);
    }
    tb.querySelectorAll("button[data-id]").forEach((b) => (b.onclick = () => viewResult(b.dataset.id)));
  } catch (e) { tb.innerHTML = `<tr><td colspan="6" class="muted">${e.message}</td></tr>`; }
}
$("refreshBtn").onclick = refreshJobs;

// ── 結果檢視 / 下載 ────────────────────────────────────
async function viewResult(id) {
  currentJob = id; $("resultMeta").textContent = "載入中…";
  try {
    const d = await api("/api/jobs/" + id);
    if (!d.pdb_url) { $("resultMeta").textContent = "結果尚未就緒"; return; }
    currentPdb = await (await fetch(d.pdb_url)).text();
    const el = $("viewer"); el.innerHTML = "";
    const v = $3Dmol.createViewer(el, { backgroundColor: "#0d0f16" });
    v.addModel(currentPdb, "pdb");
    v.setStyle({ chain: "A" }, { cartoon: { color: "#5b8cff" }, sphere: { radius: 0.5, color: "#5b8cff" } });
    v.setStyle({ chain: "B" }, { stick: { color: "#d29922" }, sphere: { radius: 0.9, color: "#d29922" } });
    v.zoomTo(); v.render();
    $("downloadBtn").disabled = false;
    const s = d.scores || {};
    $("resultMeta").textContent = `${id} · ipTM ${s.iptm ?? "—"} / pLDDT ${s.plddt ?? "—"} / 約束滿足 ${s.contact_satisfied ?? "—"}`;
  } catch (e) { $("resultMeta").textContent = e.message; }
}
$("downloadBtn").onclick = () => {
  if (!currentPdb) return;
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([currentPdb], { type: "chemical/x-pdb" }));
  a.download = `${currentJob}_complex.pdb`; a.click();
};

// ── 管理面板（admin）───────────────────────────────────
async function loadUsers() {
  const tb = $("userTable").querySelector("tbody");
  try {
    const { users } = await api("/api/admin/users");
    tb.innerHTML = "";
    for (const u of users) {
      const tr = document.createElement("tr");
      const actions = u.username === "admin" ? "" :
        `${u.status !== "active" ? `<button class="small" data-approve="${u.username}">核准</button> ` : ""}` +
        `<button class="small" data-del="${u.username}">刪除</button>`;
      tr.innerHTML = `<td>${u.username}</td><td>${u.email || "—"}</td><td>${u.role}</td>
        <td><span class="badge ${u.status === "active" ? "succeeded" : "queued"}">${u.status}</span></td>
        <td>${actions}</td>`;
      tb.appendChild(tr);
    }
    tb.querySelectorAll("[data-approve]").forEach((b) => b.onclick = async () => { await api(`/api/admin/users/${b.dataset.approve}/approve`, { method: "POST" }); loadUsers(); });
    tb.querySelectorAll("[data-del]").forEach((b) => b.onclick = async () => { if (confirm(`刪除 ${b.dataset.del}？`)) { await api(`/api/admin/users/${b.dataset.del}`, { method: "DELETE" }); loadUsers(); } });
  } catch (e) { tb.innerHTML = `<tr><td colspan="5" class="muted">${e.message}</td></tr>`; }
}
$("adminRefresh").onclick = loadUsers;

// ── init ───────────────────────────────────────────────
setInterval(() => { if (!$("app").hidden) refreshJobs(); }, 20000);
if (token()) enterApp();