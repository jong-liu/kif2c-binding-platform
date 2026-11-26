/* KIF2C Binding Platform — MVP 前端邏輯
 * 送單：用 GitHub Contents API 建 jobs/<id>.json → push 觸發 Actions。
 * 列表：讀 jobs/ 與 results/。  檢視/下載：載入 results/<id>/complex.cif。
 * MVP 以 Personal Access Token 操作；Phase 3 換成 GitHub OAuth。
 */
const $ = (id) => document.getElementById(id);
const cfg = { repo: "", token: "" };
let currentCif = null, currentJob = null, currentFmt = "pdb";

// ---------- 設定 ----------
function loadCfg() {
  cfg.repo = localStorage.getItem("kif2c_repo") || "";
  cfg.token = localStorage.getItem("kif2c_token") || "";
  $("repo").value = cfg.repo; $("token").value = cfg.token;
  $("cfgState").textContent = cfg.repo && cfg.token ? "已設定 ✓" : "尚未設定";
}
$("saveCfg").onclick = () => {
  cfg.repo = $("repo").value.trim(); cfg.token = $("token").value.trim();
  localStorage.setItem("kif2c_repo", cfg.repo);
  localStorage.setItem("kif2c_token", cfg.token);
  $("cfgState").textContent = "已儲存 ✓";
  refreshJobs();
};

// ---------- GitHub API ----------
async function gh(path, opts = {}) {
  const res = await fetch(`https://api.github.com/repos/${cfg.repo}${path}`, {
    ...opts,
    headers: {
      "Authorization": `Bearer ${cfg.token}`,
      "Accept": "application/vnd.github+json",
      ...(opts.headers || {}),
    },
  });
  if (!res.ok && res.status !== 404) throw new Error(`GitHub API ${res.status}: ${await res.text()}`);
  return res;
}
const b64 = (s) => btoa(unescape(encodeURIComponent(s)));
const unb64 = (s) => decodeURIComponent(escape(atob(s)));

// ---------- Token 估算（粗略擋 OOM）----------
function estTokens() {
  const p = $("protein").value.replace(/\s/g, "").length;
  const pep = $("peptide").value.replace(/\s/g, "").length;
  const t = p + pep;
  const warn = t > 600 ? "（⚠️ 12GB 可能 OOM）" : "";
  $("estTokens").textContent = t ? `約 ${t} residues ${warn}` : "";
  return t;
}
$("protein").oninput = estTokens; $("peptide").oninput = estTokens;

// ---------- 送單 ----------
$("submitBtn").onclick = async () => {
  if (!cfg.repo || !cfg.token) { $("submitState").textContent = "請先設定 repo/token"; return; }
  const t = estTokens();
  if (t > 600 && !confirm("估算超過 12GB 可能 OOM，仍要送出？")) return;
  const id = `job-${Date.now()}`;
  const spec = {
    id,
    created_at: new Date().toISOString(),
    protein: { chain: "A", source: "sequence", sequence: $("protein").value.replace(/\s/g, "") },
    peptide: { chain: "B", sequence: $("peptide").value.replace(/\s/g, "") },
    constraint: $("constraint").value.trim(),  // 例 "A:120-140"
    engine: $("engine").value,
    est_tokens: t,
    status: "queued",
  };
  $("submitState").textContent = "送出中…";
  try {
    await gh(`/contents/jobs/${id}.json`, {
      method: "PUT",
      body: JSON.stringify({
        message: `job: submit ${id} (${spec.engine})`,
        content: b64(JSON.stringify(spec, null, 2)),
      }),
    });
    $("submitState").textContent = `已送出 ${id} ✓`;
    refreshJobs();
  } catch (e) {
    $("submitState").textContent = "送出失敗：" + e.message;
  }
};

// ---------- Job 列表 ----------
async function listDir(dir) {
  const res = await gh(`/contents/${dir}`);
  if (res.status === 404) return [];
  return await res.json();
}
async function refreshJobs() {
  if (!cfg.repo || !cfg.token) return;
  const tbody = $("jobTable").querySelector("tbody");
  tbody.innerHTML = `<tr><td colspan="5" class="muted">載入中…</td></tr>`;
  try {
    const [jobs, results] = await Promise.all([listDir("jobs"), listDir("results")]);
    const doneIds = new Set(results.filter((r) => r.type === "dir").map((r) => r.name));
    const rows = jobs.filter((f) => f.name.endsWith(".json")).sort((a, b) => b.name.localeCompare(a.name));
    tbody.innerHTML = "";
    for (const f of rows) {
      const id = f.name.replace(".json", "");
      const done = doneIds.has(id);
      let iptm = "—", sat = "—";
      if (done) {
        try {
          const sres = await gh(`/contents/results/${id}/scores.json`);
          if (sres.ok) { const s = JSON.parse(unb64((await sres.json()).content)); iptm = (s.iptm ?? "—"); sat = s.contact_satisfied != null ? `${Math.round(s.contact_satisfied*100)}%` : "—"; }
        } catch {}
      }
      const status = done ? "succeeded" : "queued";
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${id}</td>
        <td><span class="badge ${status}">${status}</span></td>
        <td>${iptm}</td><td>${sat}</td>
        <td>${done ? `<button class="small" data-id="${id}">檢視</button>` : ""}</td>`;
      tbody.appendChild(tr);
    }
    if (!rows.length) tbody.innerHTML = `<tr><td colspan="5" class="muted">尚無 job</td></tr>`;
    tbody.querySelectorAll("button[data-id]").forEach((b) => (b.onclick = () => viewResult(b.dataset.id)));
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="5" class="muted">讀取失敗：${e.message}</td></tr>`;
  }
}
$("refreshBtn").onclick = refreshJobs;

// ---------- 結果檢視 / 下載 ----------
async function viewResult(id) {
  currentJob = id;
  $("resultMeta").textContent = "載入結構中…";
  // 先找 complex.pdb（stub），找不到再試 complex.cif（真實引擎）
  let fmt = "pdb";
  let res = await gh(`/contents/results/${id}/complex.pdb`);
  if (!res.ok) { res = await gh(`/contents/results/${id}/complex.cif`); fmt = "cif"; }
  if (!res.ok) { $("resultMeta").textContent = "找不到結構檔"; return; }
  currentFmt = fmt;
  currentCif = unb64((await res.json()).content);
  const el = $("viewer"); el.innerHTML = "";
  const v = $3Dmol.createViewer(el, { backgroundColor: "#0d0f16" });
  v.addModel(currentCif, fmt);
  v.setStyle({ chain: "A" }, { cartoon: { color: "#5b8cff" } });
  v.setStyle({ chain: "B" }, { stick: { color: "#d29922" }, cartoon: { color: "#d29922" } });
  v.zoomTo(); v.render();
  $("downloadBtn").disabled = false;
  $("resultMeta").textContent = `${id} · Chain A=藍, Chain B=金`;
}
$("downloadBtn").onclick = () => {
  if (!currentCif) return;
  const blob = new Blob([currentCif], { type: "chemical/x-" + currentFmt });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = `${currentJob}_complex.${currentFmt}`; a.click();
};

// ---------- init ----------
loadCfg();
refreshJobs();
setInterval(() => { if (cfg.repo && cfg.token) refreshJobs(); }, 20000); // 自動輪詢
