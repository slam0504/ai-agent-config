# Claude Code 設定整理（待審核）

本次將本機 `~/.claude` 的可攜設定整理成候選檔，供人工審核。`install.sh` 不讀取本目錄；正式安裝來源（`claude/CLAUDE.md`、`claude/skills/distill/`）、`install.sh` 與權限規則均未修改，也未執行安裝、commit 或 push。

## 來源

- 盤點日期：2026-09-25；本機 CLI：`Claude Code 2.1.280`。
- Repo 基準：`13c059ab7ea1ddd25e7c1ffa8b14055c2d7d1e70`。
- `~/.claude/settings.json` SHA-256：`980c9e850bbebf93d5752fa09e02851b1597bb7c601f7d9ac9f4e33af4ad19ea`。
- `~/.claude/CLAUDE.md` SHA-256：`0779c01f7d2c9962c2d207c753ac99ebc610988245d46805a97b161c400a2059`。
- 另比對 `~/.claude/skills/`、`agents/`、`hooks/`、`scripts/`、`docs/memories/approved/`，以及 repo 的 `claude/`、`memories/approved/` 與 `install.sh`。
- 這是使用者設定檔的整理，不代表目前對話採用的模型、工具或權限。

## 與正式來源的比對

| 檔案 | 狀況 | 處理 |
|---|---|---|
| `claude/CLAUDE.md` | 本機 `~/.claude/CLAUDE.md` 於 2026-08-26 被直接編輯，「Subagent 委派」一節擴寫成「Subagent 委派與模型分工（Fable 主腦 + Sonnet 執行）」，repo 來源落後 | 正式來源維持原版；本機版本放在本目錄 `CLAUDE.md` 待審，第四輪依審核修訂三處：model 敘述改為條件式（不宣稱 settings 有 `model` 欄位）、重派無進展或 Agent tool 不可用時主 agent 可在原授權範圍接手、使用者安裝的自訂 agent 依使用者要求或專案指定啟動且不必每次重問。**本目錄版本因此與本機 `~/.claude/CLAUDE.md` 不再相同**，核可後需同時更新正式來源與本機。差異可用 `diff claude/CLAUDE.md claude/review/2026-09-25/CLAUDE.md` 檢視。核准前這台機器的 `./install.sh` 會被 drift guard 擋下該檔，屬預期行為 |
| `claude/skills/distill/` | 與本機完全相同 | 不重複複製 |
| `memories/approved/` | 與本機 `~/.claude/docs/memories/approved/` 完全相同 | 不動 |

## 候選與差異

### `settings.json`（共用候選）

保留本機值，僅移除機器專屬內容，不另行調整偏好：

| 項目 | 本機現況 | 候選處理 |
|---|---|---|
| `env.PATH` | 本機絕對路徑組成 | 移至本機範例，不列入共用 |
| `permissions.allow` | 39 筆 | 共用版整個移除 `permissions.allow`：這些是歷史授權，命令名稱看似唯讀（`go run`、Makefile target、專案 script）仍可能執行寫入，不能只靠名稱判定為可攜。38 筆保留在本機範例供逐項選用，**不由 `install.sh` 自動匯入**；1 筆含公司內部 Go module 主機名稱的一次性 `find` 權限直接捨棄，不寫入 public repo。本機既有授權維持原樣 |
| `permissions.additionalDirectories` | `/Users/<user>/.claude` | 移至本機範例 |
| hooks 指令路徑 | 2 筆寫死 `/Users/<user>/.claude/hooks/...` | 改為 `$HOME/.claude/hooks/...`，與其餘 hooks 寫法一致 |
| Telegram Stop hook | 指向 `~/playground/telegram/stop_hook.py`（專案 checkout 路徑） | 移至本機範例 |
| `enabledPlugins`、`extraKnownMarketplaces`、`language`、`effortLevel`、`tui`、`editorMode` 等 | — | 原樣保留 |

權限模式旗標另外審核，候選暫時原樣保留：`permissions.defaultMode = "auto"`、`skipDangerousModePermissionPrompt`、`skipAutoPermissionPrompt`、`useAutoModeDuringPlan`。

`settings.local.example.json` 保留設定結構，實際使用者路徑改為 `/Users/example/...`。注意：Claude Code 的使用者層級設定只有單一 `~/.claude/settings.json`，沒有像 Codex 那樣的本機附加檔機制；若要跨機器安裝，`install.sh` 需要另外處理 JSON 合併，或只安裝共用部分。這是審核後的設計決定，本次未實作。

### 其他候選目錄

| 目錄 | 內容 | 相依 / 備註 |
|---|---|---|
| `hooks/` | 15 個檔案加 `tests/`（見下方「Codex 審查後的修正」）：Codex plan / implementation review gate（`codex-review-*.py`、`review-loop-*.sh`、`review_loop_common.py`、`reviewer.py`、`consume_feedback.py`、`stop_enqueue.py`、`sessionstart_status.py`）與 context checkpoint（`precompact-checkpoint.sh`、`sessionstart-restore.sh` 與對應 `.py`、`checkpoint_common.py`） | 需要 `python3` 與 Codex CLI；由 `settings.json` 的 hooks 以 `$HOME/.claude/hooks/` 引用。未收錄 `__pycache__/`、`.wrapper-error.log`、`codex-review-plan.py.bak-*`。**候選版本已修正 review-loop bug，並已全部同步回本機（第三輪 2026-09-25 15:28，第四輪 16:03）** |
| `agents/` | `code-inspector.md`、`devcontainer-test-runner.md`、`gemini.md` | 前兩者內含 agent memory 絕對路徑，已改為 `/Users/example/.claude/agent-memory/...`，安裝時需改回實際路徑。前兩者的 description 已從「完成修改後主動啟動」改為「使用者要求或專案 CLAUDE.md 指定時啟動」，與 CLAUDE.md 的委派規則一致。`gemini.md` 依賴 `scripts/gemini-bridge.sh` 與 `/usr/local/bin/gemini` |
| `scripts/` | `gemini-bridge.sh` | 唯讀 Gemini 呼叫包裝，binary 路徑寫死 `/usr/local/bin/gemini` |
| `skills/commit-ready/` | 通用 pre-commit 檢查 skill | 無專案相依。第四輪改為唯讀契約：不跑 `lint-fix` 或任何 fixer，`make test-gen` 預設不跑、需要時在暫存副本執行，報告須註明檢查涵蓋工作樹還是暫存內容。第五輪再修兩處：mock 檢查改為比對副本在產生器執行前後的差異（不再對 HEAD 比，避免誤報已更新的 mock、漏掉新增的未追蹤 mock）；第六輪把比對方式從副本內 git commit 改為刪除副本 `.git` 後以全樹 sha256 清單 diff，原因是 linked worktree 的 `.git` 是指標檔、副本 commit 會改動原工作區，且 `'*/mocks/*'` pathspec 漏掉根目錄 `mocks/`；第七輪補上失敗傳遞：雜湊管線啟用 pipefail 並檢查退出碼與空清單、產生器退出碼、`diff` 退出碼區分 0／1／大於 1，只有全部成功才可判定 mocks 一致，否則回報「檢查未完成」。第八輪提醒的使用限制：範例中的 `echo` 會讓整段 shell 仍回傳 0，必須看失敗標記與各步退出碼，不能只看整體退出碼；日後若改成自動化腳本，應讓失敗直接以非零退出；唯讀原則擴及所有語言的所有命令，執行前先讀實際腳本，無法確認不改檔就在隔離副本執行或明確回報略過 |

## 未收錄內容

| 來源 | 原因 |
|---|---|
| `skills/bo2-new-page/`、`skills/gmp-sync-execution-audit/`、`skills/n8n-monitor/` | 公司內部專案 skill，內含內部主機名稱；本 repo 為 GitHub public，不納入 |
| `skills/harness-router`、`skills/gas-harness-router` | symlink 指向其他本機 repo，不可攜 |
| `skills/synced/` | claude.ai 端自動同步的內建 skills，非使用者維護 |
| `skills-archive/`、`agent-memory/`、`plugins/`、`projects/`、`sessions/`、`settings.json.bak*` | 封存或 generated state；plugins 由 `enabledPlugins` 決定，不需同步檔案 |
| `docs/plans/`、`docs/specs/` | 本 repo 的設計文件（drift guard、Codex config portability、continuous learning loop）目前只存在於本機 `~/.claude/docs/`；是否收進 repo `docs/` 屬另一個決定，本次未處理 |

## Codex 審查後的修正

Codex 對本目錄的審查指出五項問題，四項 hook bug 經隔離環境重現確認成立，已在候選版本修正並附回歸測試；第五項（待審規則不應進安裝來源）已依審核結果把 `CLAUDE.md` 差異搬回本目錄。這些 bug 原本存在於本機 `~/.claude/hooks/` 正在跑的版本。Codex 三輪複審通過後，於 2026-09-25 15:28 將七個修正檔（`codex-review-*.py`、`review_loop_common.py`、`reviewer.py`、三個 `review-loop-*.sh`）同步回本機，舊版備份在 `~/.ai-agent-config-backup/20260925-152750/.claude/hooks/`；同步後以本機版本重跑 18 個測試全過，並實際用 Stop 與 SessionStart hook 對含中文未追蹤檔的暫存 repo 走一遍，成功產生 pending 並回報。第四輪的兩項修正（`reviewer.py` 封包內容、`sessionstart_status.py` 狀態順序）於 16:03 同步完成。

| 編號 | 問題 | 修正 |
|---|---|---|
| P1 | `cheap_worktree_fp` 只用 status 與 numstat 行數，同一行改值指紋不變；`reviewer.py finalize` 又重算目前指紋，審查期間的修改被標成已審 | 指紋改為 `git diff HEAD`、`git diff --cached HEAD` 完整 patch 加未追蹤檔原始 bytes 的 sha256；`prepare` 建 packet 時把指紋與 base SHA 寫入同一迭代的 `NNN-packet.json`，`finalize` 只讀這份 metadata，缺漏時回傳非零並拒絕完成；同一輪已有未 finalize 的 packet 時 `prepare` 拒絕再次執行並保留原 packet 與 metadata（iteration 只在 finalize 才遞增，否則第二次 prepare 會覆寫同一組檔案）；`pending.json` 只在仍指向同一棵樹時才標為已審，較新的樹保持 pending |
| P2 | `tree_dirty` 只看 `git diff`，只有新增未追蹤檔時不會排入審查，packet 也不含其內容 | `tree_dirty` 加入 `git ls-files -z --others --exclude-standard`（NUL 分隔，避免 `core.quotePath` 把中文檔名轉義成讀不到的路徑）；packet 新增「Untracked files (full content)」段落，唯讀，不動 index；讀檔失敗在指紋與 packet 中都以 `<unreadable: path>` 明確標示 |
| P3 | `codex-review-plan.py parse_decision` 掃描所有行，後面任一行以 APPROVE 開頭就算核可；第一行 `APPROVE is only an example` 也算核可 | 依 prompt 契約「第一個非空白行必須完全等於 APPROVE / REVISE / BLOCK」，兩支檔案的 parser 改為嚴格相等，`APPROVE: ok` 這類帶後綴的也回傳無判定；無判定時原本就會 deny，不會靜默核可 |
| P4 | 三個 `review-loop-*.sh` 在 `fi` 之後才取 `$?`，`RL_STRICT=1` 時仍回傳 0 | 在 `else` 分支保存失敗碼；非 strict 行為不變 |

回歸測試：

```sh
cd claude/review/2026-09-25/hooks && python3 -m unittest discover -s tests -v
```

21 個測試在修正版全部通過。前 18 個複製到同步前的原始版本執行時 16 個失敗；第四輪新增的 3 個在目前本機版本（第三輪）上 2 個失敗，其餘為正向對照組。

Codex 第二輪複審指出第一版修正的三個缺口，已一併修正並各補回歸測試：`finalize` 讀可被下一次 Stop 覆寫的 `pending.json`（改讀 per-packet metadata）；未追蹤檔路徑未用 `-z` 且以 UTF-8 replacement 解碼，中文檔名讀不到、不同二進位內容指紋相同（改 NUL 分隔、雜湊原始 bytes）；verdict 只比對第一個字（改嚴格相等）。另外主 agent 補了一個 subagent 標出的殘留：`finalize` 原本無條件把 `pending.json` 標為已審，會吞掉較新樹的待審標記。Codex 第三輪複審再指出同一輪重複 `prepare` 會覆寫 `001-packet.*`，讓 A 的回饋被蓋成 B 已審；已改為拒絕重複 prepare 並補測試。副作用：想放棄 A 直接改審 B 時，必須先 finalize A，本次不提供強制覆寫選項。

Codex 第四輪（審核範圍 `13c059a..02c4912`）再重現兩項 hook 正確性問題，已修正並各補測試：packet 只收 `git diff HEAD`，「先暫存 999、再把工作檔還原」的變更不會出現在封包，但指紋有算進去，仍可 finalize 為 pass，現改為分開呈現 staged 與 unstaged 的 stat 與完整 diff；`sessionstart_status` 在檢查新 pending 前就因上一輪 `done` 回報 idle，現改為先看 `pending.json` 是否為 pending。這兩項修正於 Codex 第八輪通過後（2026-09-25 16:03）同步回本機，舊版備份在 `~/.ai-agent-config-backup/20260925-160324/.claude/hooks/`；同步後以本機版本重跑 21 個測試全過，並實測「暫存 999 後還原工作檔」的封包含 999、上一輪 done 後新 pending 的 SessionStart 回報 pending review。

剩餘風險：P1 的指紋現在會讀取所有未追蹤檔內容，若專案沒有 `.gitignore` 且有大量未追蹤檔（例如 `node_modules/`），Stop hook 的成本會明顯上升；原版以行數計算所以便宜。Codex 建議不要改用大小與 mtime（會再漏掉內容變更），而是設容量上限、超限時明確標為未完成審查。本次未實作，列為後續項目。

## 驗證

- 兩個 JSON 候選檔可被 `json.load` 解析。
- 候選目錄內以 `grep` 確認不含實際使用者名稱、API key、token 樣式字串或內部主機名稱。
- `test/test_install.sh` 與 `test/test_drift_guard.sh` 皆 PASS（`install.sh` 未改動）。
- hooks 回歸測試 21 個通過；所有 `.py` 通過 `py_compile`、所有 `.sh` 通過 `bash -n`。
- 測試產生的 `__pycache__/` 已清除，並在 repo `.gitignore` 加入 `__pycache__/` 與 `*.pyc`。
- 未執行：hooks / agents / skills 在另一台機器上的實際安裝與運作。

## Codex 第四輪對其他待決項目的意見

| 項目 | 意見 |
|---|---|
| Codex `high`、`low`、子代理預設 | 欄位符合官方參考；可作偏好候選，未驗證執行與用量效果 |
| Sepia、Playwright 共用 | 建議列為可選安裝；`@latest` 無法固定各機器版本 |
| 納入 `install.sh` | 暫緩整批納入；先處理 agents 的 `/Users/example/` 與執行檔路徑，再驗證安裝 |
| Claude 設定合併 | 保留未管理的本機欄位；permissions 與 hooks 用明確合併規則，不整檔覆蓋、不單純串接陣列 |

## 審核後的後續決定

1. `settings.json`：接受共用候選的取捨，並決定 `install.sh` 是否安裝它（含 JSON 合併策略）。
2. `hooks/`、`agents/`、`scripts/`、`skills/commit-ready/`：決定是否納入 `install.sh`，以及是否比照 `memories/approved/` 豁免 drift guard。
3. `CLAUDE.md`：Sonnet 委派規則是否核可為跨機器規則；核可後以本目錄版本覆蓋 `claude/CLAUDE.md`。
4. hooks 修正已全部同步回本機（第三輪 15:28、第四輪 16:03）。候選與本機 15 個 hook 檔案目前一致。
5. 未追蹤檔內容雜湊的容量上限與超限標示，另開一次修改。
6. 核准的項目從本目錄移到 `claude/` 正式位置後，再更新 `install.sh` 與根目錄 README。
