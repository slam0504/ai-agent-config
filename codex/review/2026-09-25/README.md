# Codex 設定整理（待審核）

本次將本機設定拆成共用候選與本機範例，供人工審核。`install.sh` 不讀取本目錄；正式模板、本機設定與權限規則均未修改，也未執行正式安裝、commit 或 push。

## 來源

- 盤點日期：2026-09-25；本機 CLI：`codex-cli 0.156.1`。
- Repo 基準：`13c059ab7ea1ddd25e7c1ffa8b14055c2d7d1e70`。
- 設定來源：`~/.codex/config.toml`；SHA-256：`169572230d2d2c790324d80d9856b11525a9baa09f2b68d0d955e15c59dc3963`。
- 另比對 `~/.codex/AGENTS.md`、`~/.agents/skills/distill/`、`~/.codex/rules/default.rules`，以及 repo 的模板、本機附加設定與安裝腳本。
- 這是使用者設定檔的整理，不代表目前對話採用的模型、工具或權限；對話與執行環境可能另有設定。

## 候選與差異

[共用設定候選](config.toml.template)保留本機值，不另行升級模型或調整參數。

| 項目 | Repo 正式模板 | 本機現況／候選 |
|---|---|---|
| 主模型 | `gpt-5.6-sol` | 相同 |
| 推理強度 | `medium` | `high` |
| 回覆長度 | 未設定 | `model_verbosity = "low"` |
| 服務等級、memories、GitHub plugin | `priority`、啟用、啟用 | 相同 |
| 子代理 | 未設定 | `gpt-5.6-terra`、`medium`、同時最多 3 個子代理 |
| Sepia | 未設定 | 啟用 plugin，收錄 Git marketplace 來源 |
| Playwright MCP | 未設定 | `npx -y @playwright/mcp@latest` |
| TUI 提示狀態 | 收錄 `gpt-5.5` 提示計數 | 候選移至本機範例，不列入共用模板 |

子代理設定的預設模型、推理強度與並行上限（不含主代理），以及 MCP 的 command／args／timeout 欄位，已對照 [OpenAI 官方設定參考](https://learn.chatgpt.com/docs/config-file/config-reference)。此檢查不代表所有模型、plugin 或 MCP 已完成執行驗證。

## 本機設定與未收錄內容

[本機附加設定範例](config.local.toml.example)保留設定結構，實際使用者與專案路徑改為 `/Users/example/...`。

| 來源 | 本次處理 |
|---|---|
| 專案信任 | 本機有 34 筆，repo 的 gitignored 本機檔有 20 筆，少了 14 筆；不將實際路徑或信任授權納入共用設定 |
| zhtw MCP | 執行檔為本機絕對路徑，放入範例 |
| agent-mailroom MCP | 執行檔為本機 virtualenv 路徑，放入範例；保留 localhost URL 與 45 秒 timeout |
| TUI 狀態 | 本機範例保留螢幕閱讀器偵測與模型提示計數 |
| `AGENTS.md` | 與 repo 完全相同，不重複複製 |
| `distill` skill | 與 repo 完全相同，不重複複製 |
| 其他 skills | 兩個 harness router 為外部 repo 的符號連結；系統與 plugin skills 由各自來源管理，本次不複製 |
| `rules/default.rules` | 9 筆 allow 規則：4 筆一般命令字首（`kubectl`、`glab mr view`、`git add`、特定 `curl` 選項），5 筆歷史查詢／job 規則；僅盤點，不移植授權 |
| `config.toml.bak-20260915-mailroom` | 本機歷史備份，不作為目前設定來源，也不收錄 |
| 憑證與執行狀態 | 不讀取或複製 `auth.json` 內容；不收錄對話、logs、SQLite、原始 memories、快取與備份 |

## 審核事項

- 是否將 `high` 推理強度、`low` 回覆長度及子代理預設值設為跨機器共用偏好。較高推理強度與並行工作可能影響時間與用量，本次不估算費用。
- 是否共用 Sepia 與 Playwright 設定。候選沿用 `@latest`，未固定 Playwright 版本；plugin 啟用設定本身也不代表另一台機器已安裝相依套件。
- 是否將 TUI 提示狀態移出正式模板，改由各機器保留。
- 本機附加設定需另外整合：若日後直接以候選模板加目前僅有 20 筆專案的本機檔強制安裝，會遺漏另外 14 筆信任設定、兩個本機 MCP 與 TUI 狀態。一般安裝的 drift guard 會跳過不一致的目的檔。
- 不將現有 allow 規則視為跨機器授權。若日後要同步，須另行審核命令範圍與安裝方式。

核可後，再將核可項目納入 `codex/config.toml.template` 與 `codex/config.local.toml.example`，並於各機器整合 gitignored 本機檔。本次沒有變更這些安裝來源。

本機整合時，應先重新比對 `~/.codex/config.toml` 與 `codex/config.local.toml`，從前者補入後者缺少的 `[projects.*]` 區塊（本次盤點為 14 筆）、`[mcp_servers.zhtw]`、`[mcp_servers.agent-mailroom]` 與 TUI 狀態。保留實際本機路徑，不以範例覆蓋既有本機檔；完成後先解析串接結果並與本機設定比對，再執行安裝。

## 驗證

驗證範圍為 TOML 解析、與來源值的比對、候選及附加設定串接、敏感資料與真實路徑檢查，以及隔離環境中的既有安裝測試。未啟動 MCP、呼叫模型、安裝 plugin 或驗證另一台機器；執行相容性仍待後續確認。

本次結果：

- TOML 解析通過；候選與本機範例、候選與既有本機檔，兩種串接均可解析，沒有重複 table。
- 共用候選與來源相應欄位一致；本機 MCP 範例僅替換執行檔路徑，其他值與 TUI 狀態一致。
- 候選未出現真實 home 路徑或常見憑證格式；此為格式掃描與人工檢視，非完整 secret scanner。
- `sh test/test_install.sh`、`sh test/test_drift_guard.sh` 均通過。
- 額外在暫存 home 執行安裝，比對安裝結果確實來自正式模板及既有本機檔，待審核目錄未被複製。
- `git diff --check` 通過；新檔另檢查行尾空白。本機設定 SHA-256 未變，`AGENTS.md` 仍與 repo 相同。
