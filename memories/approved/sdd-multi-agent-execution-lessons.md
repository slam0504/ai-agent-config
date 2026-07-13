---
status: approved
scope: global
applies_to: both
confidence: verified
verified_on: 2026-07-08
source: distill
reviewed_by: slam0504
---

# SDD（多代理計畫執行）實戰教訓

從 stellaris-advisor 專案（12 任務 subagent-driven TDD、逐任務兩階段審查、最終全分支審查）驗證的跨工具教訓：

1. **Plan 內的範例碼必須視為未審查程式碼**。implementer 會忠實轉錄 plan 自帶的 bug——本案 4 個真實缺陷（stat 競態違反 no-raise 契約、SQLite `check_same_thread` 跨執行緒靜默寫入失敗、backfill 亂序 history 產生錯誤結論、CLI 函式內 shadow-import crash）全部源自 plan 範例碼。審查層是唯一防線，寫 plan 的人不能同時當唯一守門員。
2. **Review prompt 要主動指定高風險假設**，不能只給通用審查指令。本案 HIGH 級缺陷（跨執行緒 DB 連線）是因為 dispatch prompt 明確要求「驗證 worker thread 使用 main thread 建立的 sqlite connection 是否會炸」才被抓到；通用 review 兩次放行。
3. **給 reviewer 的 context 裁剪會製造誤報/漏報**。兩次誤報（schema 欄位被判 scope creep、spec 章節被判不存在）都因 controller 濃縮 constraints 時漏掉原始 spec 細節。裁剪省 token 的同時要意識到：reviewer 只能依你給的事實判斷。
4. **最終 whole-branch review 仍必要**，不因逐任務審查全過而省略。本案 12 個任務審查全數通過後，全分支審查仍抓出 4 個 Important（含兩個真實行為 bug）——跨任務互動與 plan 自相矛盾只有全景視角看得到。
5. **CLI／真實入口路徑要有測試**。80+ 單元測試全綠，但 argv → main() 這條真實路徑零覆蓋，首次真實執行即 crash。組裝層／入口層至少要一條煙霧測試。

## 證據

- stellaris-mods repo：commits `56fc360`（stat 競態修復）、`99abe5f`（check_same_thread）、`6406e83`（backfill 排序等最終批次）、`f2d37ff`（CLI shadow-import + 入口測試）
- 執行 ledger：stellaris-mods `.superpowers/sdd/progress.md`
