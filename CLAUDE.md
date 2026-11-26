# KIF2C Binding Platform — 專案藍圖

> 本檔是長期藍圖（變動慢，自動載入）。進度日誌看 `工作筆記.md`（變動快）。
> 全機最高指導原則見 `~/.claude/CLAUDE.md`，衝突時以全域為準。

## 專案一句話

一個 **Protein–Peptide Binding-Site Constrained 結構預測平台**：使用者在 GitHub 介面登入、輸入蛋白質（Chain A）與 peptide（Chain B）與結合位點限制，運算**派回本機 RTX 3060（self-hosted runner）**執行開源 AF3 衍生模型（Chai-1 / Boltz-2），結果回傳前端可視化與下載。

完整規格見 **`docs/ARCHITECTURE.md`**（可行性、技術比較、架構圖、DB schema、API、roadmap）。

## 一桌三櫃

- 🪑 **工作桌（本機）**：`/home/jong/kif2c-binding-platform`（git + GPU 運算都在這）
- ☁️ **雲端同步**：Google Drive `claude/projects/kif2c-binding-platform/`，用 `kif2c-sync` 雙向同步（排除 `.git`/`.claude`）
- 🐙 **GitHub**：public repo + Pages（前端的家、Actions 派發運算）— 待 `gh auth login` 後建立
- 📘 **Obsidian**：尚未設定 vault（之後補）
- 🔥 **Firebase**：目前不用（會員走 GitHub OAuth；資料走 GitHub/SQLite）

## 真實硬體與邊界條件（重要）

- **GPU：單張 RTX 3060 / 12GB VRAM**，開發兼運算同一台。
- 12GB 僅能跑**小型系統**（蛋白 ≤ ~400–600 殘基 + 短 peptide），需 low-memory/chunking。大蛋白跑不動 → 這是 MVP 硬限制。
- 單 GPU → runner 併發 = 1，job 排隊循序處理。大量 batch 靠排隊，不是平行。
- prompt 裡的 K8s / GPU cluster / 雲端 → 列為 **Phase 4 擴展路線**，非 MVP。

## 引擎選型（結論）

| | 授權 | Constraints | 本機 12GB |
|---|---|---|---|
| **Chai-1** | Apache 2.0（可商用） | pocket / contact / docking | 小系統可 |
| **Boltz-2** | MIT（可商用） | pocket / contact + steering（強制） | 小系統可，affinity head 對 peptide 不可靠 |
| AlphaFold3 | 權重商用受限 | ✅ | ❌ 不選 |

主引擎 **Chai-1**（約束最直覺、Apache 可商用）；**Boltz-2** 作為對照/備援。

## 工作模式（觸發詞）

- 加新模組：說「我想做一個 XXX」→ 建對應子資料夾
- 「開工」→ 讀工作筆記 + git 狀態 + 建議下一步
- 「收工」→ 更新工作筆記 + `kif2c-sync` + git commit/push

## 鐵則

- 🔥 `.claude/` 永不 commit（已在 `.gitignore`）。
- 機密（OAuth client secret、token、rclone.conf）絕不進 repo；前端不寫死 secret。
- 模型權重、運算輸出（`.cif`/`.pdb`/MSA）不進 repo，走 Pages/Drive/artifacts。
- 雲端 git 操作前已設 `windows.appendAtomically false`。
- commit message 寫「做了什麼＋為什麼」，不寫「更新」「修改」。
