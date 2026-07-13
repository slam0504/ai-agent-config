---
status: review
scope: global
applies_to: both
confidence: assumed
verified_on: 2026-07-13
source: distill
reviewed_by:
---

# 服務重啟後驗證 listener process identity

重啟本機服務後，「endpoint 回 200」與「下游副作用有發生」都不足以證明新版
code 已生效——舊 process 若仍佔著 port，新 process 可能啟動失敗並靜默退出，
所有健康訊號仍由舊 process 提供。

**規則**：重啟驗證必須確認「監聽該 port 的 process 身分」。例如先用
`lsof -nP -iTCP:<port> -sTCP:LISTEN` 只取得 TCP listener PID，再依作業系統
可用方式檢查 executable／command 與啟動時間，並和重啟前的 PID 比對，確認
listener 確實已換成剛啟動的 instance。

**Go-specific evidence（2026-07-13, arkham-docs-server）**：
- `pkill -f "cmd/server"` 只匹配 `go run ./cmd/server` 父程序，殺不到它編譯出
  的子 binary（程序名只是 `server`、位於 temp 路徑）
- 舊 process 佔 `:8080` → 新 instance `bind: address already in use` fatal
  退出；`readyz=200` 與 outbox 清空兩個訊號皆由舊 process 產生，造成
  「已用新 code 重送」的誤報
- 緩解方式：`go build` 出固定路徑的獨立 binary 再啟動，或交由 service manager
  管理 PID 與生命週期，讓 process 身分與啟動失敗都可查證

尚未在其他 runtime / 專案重複驗證，故 confidence: assumed；其他語言的
process 樹行為不必然相同。
