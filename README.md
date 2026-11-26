# 🧬 KIF2C Binding Platform

Protein–Peptide 結合位點約束結構預測平台。
**GitHub 前端送單 → 運算派回本機 RTX 3060（self-hosted runner）→ 結果回前端呈現與下載。**

- Chain A = Protein，Chain B = Peptide，所有約束對象永遠是 Chain A。
- 引擎：Chai-1（主，Apache 2.0）/ Boltz-2（備，MIT）。MVP 先用 `stub` 假引擎打通管線。
- 完整規格（可行性/比較/schema/API/roadmap）：[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)（參考用，暫不加工）。

## 管線

```
前端(Pages) --建 jobs/<id>.json--> Repo --push 觸發--> Actions
   --派到 self-hosted runner(RTX3060)--> run_prediction.py --commit results/<id>/--> 前端輪詢顯示+下載
```

## 目錄

| 路徑 | 說明 |
|------|------|
| `frontend/` | GitHub Pages 靜態前端（送單 / job 列表 / 3Dmol 檢視 / 下載） |
| `.github/workflows/predict.yml` | push `jobs/**` 觸發，跑在 self-hosted GPU runner |
| `runner/run_prediction.py` | 預測入口（目前 stub；真實引擎接 `run_real_engine()`） |
| `runner/constraints/parser.py` | 約束解析：`A:120-140` → restraint |
| `jobs/` · `results/` | job spec 進來、結果出去 |
| `examples/` | 範例 job 與 stub 結果 |

## 設定步驟（一次性）

> 需要你本人操作的用 👤 標記。

1. 👤 **GitHub 登入**：`export PATH="$HOME/.local/bin:$PATH" && gh auth login`
2. **建 repo**（建議 private，因 self-hosted runner 會跑 job 內容）：
   `gh repo create kif2c-binding-platform --private --source=. --push`
3. **開 GitHub Pages**：Settings → Pages → Source 選 `main` 的 `/frontend`（或改發 `gh-pages`）。
4. 👤 **註冊 self-hosted runner**（在這台 RTX 3060）：
   repo → Settings → Actions → Runners → New self-hosted runner → 照指令安裝，
   **標籤加上 `gpu`**（workflow 用 `runs-on: [self-hosted, gpu]`）。
5. 👤 **產 Personal Access Token**（fine-grained，對本 repo 有 Contents 讀寫），貼進前端「連線設定」。
6. **測通管線**：前端用 `engine=stub` 送一張單 → runner 跑 → 結果顯示可下載。
7. **換真實引擎**：裝 Chai-1，於 `run_prediction.py` 的 `run_real_engine()` 接上（見該函式 TODO）。

## 本機快速測試（不經 GitHub）

```bash
python3 runner/run_prediction.py --spec examples/job-sample.json --out results/job-sample
cat results/job-sample/scores.json
```

## 硬體邊界

單張 RTX 3060 (12GB)：MVP 鎖定小型系統（蛋白 ≤ ~400–600 殘基 + 短 peptide）。
大型系統需 24GB+ 或雲端 GPU（Phase 4）。前端送單前會估 token 擋 OOM。
