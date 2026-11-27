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

// ── Peptide 輸入模式：single / multiple(CSV) ────────────
let peptideMode = "single";
let csvPeptides = []; // [{name, seq}]
const AA_RE = /^[ACDEFGHIKLMNPQRSTVWY]+$/;

function setMode(m) {
  peptideMode = m;
  $("modeSingle").classList.toggle("active", m === "single");
  $("modeMulti").classList.toggle("active", m === "multi");
  $("singlePane").hidden = m !== "single";
  $("multiPane").hidden = m !== "multi";
  $("submitBtn").textContent = m === "multi" ? "批次送出 Jobs" : "送出 Job";
  estTokens();
}
$("modeSingle").onclick = () => setMode("single");
$("modeMulti").onclick = () => setMode("multi");

function parsePeptideCsv(text) {
  const rows = [];
  const HEADER_RE = /^(name|id|label|peptide|seq|sequence)$/i;
  const lines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  lines.forEach((line, i) => {
    const cols = line.split(",").map((c) => c.trim());
    let seq = (cols.length >= 2 ? cols[1] : cols[0] || "").toUpperCase().replace(/\s/g, "");
    // 標題列（第一列，且任一欄位是 name/peptide/seq… 這類關鍵字）→ 略過
    if (i === 0 && cols.some((c) => HEADER_RE.test(c))) return;
    if (!seq) return;
    if (!AA_RE.test(seq)) throw new Error(`第 ${i + 1} 行含非胺基酸字元：${seq}`);
    const name = cols.length >= 2 && cols[0] ? cols[0] : `pep${rows.length + 1}`;
    rows.push({ name, seq });
  });
  if (!rows.length) throw new Error("CSV 沒有有效的 peptide 序列");
  return rows;
}

$("peptideCsv").onchange = async (e) => {
  csvPeptides = [];
  const f = e.target.files[0];
  if (!f) { $("csvPreview").textContent = ""; estTokens(); return; }
  try {
    csvPeptides = parsePeptideCsv(await f.text());
    const head = csvPeptides.slice(0, 5).map((p) => `${p.name}(${p.seq.length}aa)`).join("、");
    $("csvPreview").innerHTML = `✓ 讀到 <b>${csvPeptides.length}</b> 個 peptide：${head}${csvPeptides.length > 5 ? " …" : ""}`;
    $("csvPreview").style.color = "var(--ok)";
  } catch (err) {
    $("csvPreview").textContent = "✗ " + err.message;
    $("csvPreview").style.color = "var(--err)";
  }
  estTokens();
};

$("dlCsvTemplate").onclick = (e) => {
  e.preventDefault();
  const blob = new Blob(["name,peptide\npep1,RPKLGYAA\npep2,GKATCFAYGQ\npep3,LVDLAGNER\n"], { type: "text/csv" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = "peptides_template.csv"; a.click();
};

// ── Token 估算 ─────────────────────────────────────────
function estTokens() {
  const prot = $("protein").value.replace(/\s/g, "").length;
  if (peptideMode === "multi") {
    $("estTokens").textContent = csvPeptides.length
      ? `${csvPeptides.length} 個 peptide，將各送一個 job（每個 ≈ ${prot}+peptide residues）`
      : "";
    return;
  }
  const t = prot + $("peptide").value.replace(/\s/g, "").length;
  $("estTokens").textContent = t ? `約 ${t} residues${t > 600 ? " ⚠️ 12GB 可能 OOM" : ""}` : "";
}
$("protein").oninput = estTokens; $("peptide").oninput = estTokens;

// ── 送單（single 一個 / multiple 批次）──────────────────
$("submitBtn").onclick = async () => {
  const protein = $("protein").value.replace(/\s/g, "");
  const constraint = $("constraint").value.trim();
  const engine = $("engine").value;
  $("submitState").style.color = "";

  if (peptideMode === "single") {
    $("submitState").textContent = "送出中…";
    try {
      const d = await api("/api/jobs", {
        method: "POST",
        body: JSON.stringify({ protein, peptide: $("peptide").value.replace(/\s/g, ""), constraint, engine }),
      });
      $("submitState").textContent = `已送出 ${d.job_id} ✓`;
      refreshJobs();
    } catch (e) { $("submitState").style.color = "var(--err)"; $("submitState").textContent = "失敗：" + e.message; }
    return;
  }

  // multiple：逐條送出（單 GPU → runner 會自行排隊循序處理）
  if (!csvPeptides.length) { $("submitState").style.color = "var(--err)"; $("submitState").textContent = "請先上傳有效的 CSV"; return; }
  $("submitBtn").disabled = true;
  let ok = 0; const fails = [];
  for (let i = 0; i < csvPeptides.length; i++) {
    const p = csvPeptides[i];
    $("submitState").textContent = `批次送出中… ${i + 1}/${csvPeptides.length}（${p.name}）`;
    try {
      await api("/api/jobs", {
        method: "POST",
        body: JSON.stringify({ protein, peptide: p.seq, constraint, engine, label: p.name }),
      });
      ok++;
    } catch (e) { fails.push(`${p.name}：${e.message}`); }
  }
  $("submitBtn").disabled = false;
  $("submitState").style.color = fails.length ? "var(--warn)" : "var(--ok)";
  $("submitState").textContent = `批次完成：成功 ${ok} / ${csvPeptides.length}` +
    (fails.length ? `，失敗 ${fails.length}（${fails.slice(0, 3).join("；")}${fails.length > 3 ? " …" : ""}）` : "");
  refreshJobs();
};

// ── Jobs 列表 ──────────────────────────────────────────
async function refreshJobs() {
  const tb = $("jobTable").querySelector("tbody");
  tb.innerHTML = `<tr><td colspan="7" class="muted">載入中…</td></tr>`;
  try {
    const { jobs } = await api("/api/jobs");
    tb.innerHTML = "";
    if (!jobs.length) { tb.innerHTML = `<tr><td colspan="7" class="muted">尚無 job</td></tr>`; return; }
    for (const j of jobs) {
      const tr = document.createElement("tr");
      const done = j.status === "succeeded";
      const failed = j.status === "failed";
      const running = j.status === "running";
      const elapsed = running && j.created_at
        ? ` <span class="muted elapsed" data-start="${j.created_at}">· ${fmtElapsed(j.created_at)}</span>` : "";
      tr.innerHTML = `<td>${j.job_id}</td>
        <td>${j.label || "—"}</td>
        <td><span class="badge ${done ? "succeeded" : failed ? "failed" : "running"}">${j.status}</span>${elapsed}</td>
        <td>${j.iptm ?? "—"}</td><td>${j.plddt ?? "—"}</td>
        <td>${j.constraint || "—"}</td>
        <td>${done ? `<button class="small" data-id="${j.job_id}">檢視</button> ` : ""}${running ? `<button class="small" data-prog="${j.job_id}">進度</button> ` : ""}<button class="small danger" data-del="${j.job_id}">刪除</button></td>`;
      tb.appendChild(tr);
    }
    tb.querySelectorAll("button[data-id]").forEach((b) => (b.onclick = () => viewResult(b.dataset.id)));
    tb.querySelectorAll("button[data-prog]").forEach((b) => (b.onclick = () => showProgress(b.dataset.prog)));
    tb.querySelectorAll("button[data-del]").forEach((b) => (b.onclick = () => deleteJob(b.dataset.del)));
  } catch (e) { tb.innerHTML = `<tr><td colspan="7" class="muted">${e.message}</td></tr>`; }
}
$("refreshBtn").onclick = refreshJobs;

// 經過時間格式化（ISO 8601 → 「2分10秒」）
function fmtElapsed(isoTs) {
  const sec = Math.max(0, Math.floor((Date.now() - Date.parse(isoTs)) / 1000));
  const m = Math.floor(sec / 60), s = sec % 60;
  return m ? `已 ${m}分${s}秒` : `已 ${s}秒`;
}
// 每秒刷新 running 列的經過時間（不打後端）
setInterval(() => {
  document.querySelectorAll(".elapsed[data-start]").forEach((el) => {
    el.textContent = "· " + fmtElapsed(el.dataset.start);
  });
}, 1000);

// 查某 running job 的即時進度（呼叫後端 → GitHub Actions）
async function showProgress(id) {
  $("resultMeta").textContent = `讀取 ${id} 進度中…`;
  currentJob = null; currentPdb = null;
  $("downloadBtn").disabled = true; $("viewer").innerHTML = "";
  try {
    const d = await api("/api/jobs/" + id);
    if (d.status !== "running") { $("resultMeta").textContent = `${id} 已 ${d.status}，請按「↻」刷新列表`; refreshJobs(); return; }
    const p = d.progress || {};
    const step = (p.step_index && p.total_steps) ? ` · 第 ${p.step_index}/${p.total_steps} 步` : "";
    const el = (p.elapsed_sec != null) ? ` · 已 ${Math.floor(p.elapsed_sec / 60)}分${p.elapsed_sec % 60}秒` : "";
    const link = p.run_url ? `　<a href="${p.run_url}" target="_blank" rel="noopener">Actions ↗</a>` : "";
    $("resultMeta").innerHTML = `⏳ <b>${id}</b> · ${p.stage || "執行中…"}${step}${el}${link}`;
  } catch (e) { $("resultMeta").textContent = "進度讀取失敗：" + e.message; }
}

async function deleteJob(id) {
  if (!confirm(`確定刪除 ${id}？\n將一併移除 GitHub 上的 job 與結果檔，無法復原。`)) return;
  try {
    await api("/api/jobs/" + id, { method: "DELETE" });
    if (currentJob === id) { // 若正在檢視這個 job，一併清掉檢視區
      currentJob = null; currentPdb = null;
      $("downloadBtn").disabled = true; $("resultMeta").textContent = ""; $("viewer").innerHTML = "";
    }
    refreshJobs();
  } catch (e) { alert("刪除失敗：" + e.message); }
}

// ── 結構檢視器（3Dmol）────────────────────────────────
let viewer3d = null, surfaceOn = false, spinning = false, currentRep = "cartoon";
const CHAIN_COLOR = { A: "#5b8cff", B: "#d29922" }; // A=protein 藍、B=peptide 橘

// 套用主要表現法（cartoon / stick / sphere），依 chain 上色
function setRep(mode) {
  if (!viewer3d) return;
  currentRep = mode;
  viewer3d.setStyle({}, {}); // 清空既有樣式（不動 surface）
  if (mode === "cartoon") {
    viewer3d.setStyle({ chain: "A" }, { cartoon: { color: CHAIN_COLOR.A } });
    // peptide 多半短，cartoon 外再疊細 stick 讓它看得見
    viewer3d.setStyle({ chain: "B" }, { cartoon: { color: CHAIN_COLOR.B }, stick: { color: CHAIN_COLOR.B, radius: 0.15 } });
  } else if (mode === "stick") {
    viewer3d.setStyle({ chain: "A" }, { stick: { color: CHAIN_COLOR.A, radius: 0.18 } });
    viewer3d.setStyle({ chain: "B" }, { stick: { color: CHAIN_COLOR.B, radius: 0.22 } });
  } else if (mode === "sphere") {
    viewer3d.setStyle({ chain: "A" }, { sphere: { color: CHAIN_COLOR.A } });
    viewer3d.setStyle({ chain: "B" }, { sphere: { color: CHAIN_COLOR.B } });
  }
  viewer3d.render();
  document.querySelectorAll(".vrep").forEach((b) => b.classList.toggle("active", b.dataset.rep === mode));
}

function toggleSurface() {
  if (!viewer3d) return;
  if (surfaceOn) { viewer3d.removeAllSurfaces(); surfaceOn = false; }
  else { viewer3d.addSurface($3Dmol.SurfaceType.VDW, { opacity: 0.7, color: "#8b90a0" }, { chain: "A" }); surfaceOn = true; }
  viewer3d.render();
  $("btnSurface").classList.toggle("active", surfaceOn);
}

function toggleSpin() {
  if (!viewer3d) return;
  spinning = !spinning;
  viewer3d.spin(spinning ? "y" : false);
  $("btnRotate").classList.toggle("active", spinning);
}

function resetView() {
  if (!viewer3d) return;
  if (surfaceOn) { viewer3d.removeAllSurfaces(); surfaceOn = false; $("btnSurface").classList.remove("active"); }
  if (spinning) { spinning = false; viewer3d.spin(false); $("btnRotate").classList.remove("active"); }
  setRep("cartoon");       // 回到預設 cartoon
  viewer3d.zoomTo(); viewer3d.render();
}

// 控制鈕（只需綁一次）
document.querySelectorAll(".vrep").forEach((b) => (b.onclick = () => setRep(b.dataset.rep)));
$("btnSurface").onclick = toggleSurface;
$("btnRotate").onclick = toggleSpin;
$("btnReset").onclick = resetView;

// ── 結果檢視 / 下載 ────────────────────────────────────
async function viewResult(id) {
  currentJob = id; $("resultMeta").textContent = "載入中…";
  try {
    const d = await api("/api/jobs/" + id);
    if (!d.pdb_url) { $("resultMeta").textContent = "結果尚未就緒"; return; }
    currentPdb = await (await fetch(d.pdb_url)).text();
    const el = $("viewer"); el.innerHTML = "";
    viewer3d = $3Dmol.createViewer(el, { backgroundColor: "#0d0f16" });
    viewer3d.addModel(currentPdb, "pdb");
    surfaceOn = false; spinning = false;
    $("btnSurface").classList.remove("active"); $("btnRotate").classList.remove("active");
    setRep("cartoon");       // 預設 cartoon 顯示
    viewer3d.zoomTo(); viewer3d.render();
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
estTokens(); // 預設序列已帶入 → 載入即顯示殘基數估算
setInterval(() => { if (!$("app").hidden) refreshJobs(); }, 20000);
if (token()) enterApp();