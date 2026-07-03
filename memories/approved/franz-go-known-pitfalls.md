---
status: approved
scope: global
applies_to: both
confidence: verified
verified_on: 2026-07-03
source: distill
reviewed_by: slam0504
---

# franz-go 踩雷集(實測確認)

任何專案使用 `github.com/twmb/franz-go` 前先讀。三條均於 2026-07-03 在
asurada kafka-franz driver 開發期間實測確認(kfake rebalance 測試 + 原始碼)。

## 1. cursor race(v1.20.6 與 v1.21.5 均存在,upstream 未修)

rebalance 邊界的 offset list/epoch load 與並發 `PollFetches` 會同時寫同一
cursor offset(`takeBuffered → cursor.setOffset` vs
`handleListOrEpochResults → cursor.setOffset`,source.go)。

- 重現:consumer group + rebalance(成員加入)期間持續 poll,`go test -race
  -count=5` 穩定命中
- v1.21.5 的 `listOrEpochMu` 修的是兩個 handleListOrEpochResults 互撞,
  不是 poll-vs-load 這條 → 升級不解
- 危害:cursorOffset 為多欄位 struct 非原子寫;交錯結果為兩個合法 offset
  之一(重複消費)或 epoch 錯配(觸發 revalidation 自癒);無法嚴格排除從
  錯誤 offset 消費
- caller 側無修法(cursor 為私有結構、load 無完成信號;`BlockRebalanceOnPoll`
  不涵蓋 load 且會讓慢 poll 拖住 rebalance)→ 只能向 upstream 回報或
  fork + patch

## 2. pause 狀態跨 rebalance 殘留(設計行為,易踩)

`PauseFetchPartitions` 的狀態存於 `kgo.Client`,「persist until resumed」
(v1.20.6 consumer.go:587);`storePaused` 只有 Pause/Resume API 會呼叫,
**rebalance / assign / revoke 都不清除**。

- 後果:背壓 pause 中的 partition 被 revoke 後再 assign 回同一 client 時,
  fetch 永久停擺(cooperative-sticky 下 partition 回到原 client 很常見)
- 呼叫端義務:pause 的擁有者在生命週期終點(revoke / shutdown)必須自行
  resume;且 pause/resume 呼叫要與清理路徑用同一把鎖序列化,否則 pause
  可能落在清理的 resume 之後照樣殘留

## 3. 版本門檻:v1.21+ 需 go 1.25

franz-go v1.21.x 全系列 go.mod 要求 `go 1.25.0`;CI toolchain 較舊
(如 go 1.24)時只能停在 v1.20.6(1.20 線最後一版)。

- 連帶影響:上游未來所有修復(含第 1 條的 fix)都會出在 go 1.25+ 的版本,
  CI 不升 go 就吃不到 → 依賴此庫時把 CI go 版本升級排進規劃
- `go get` 新依賴前先查其 go directive 要求 vs CI 版本,避免 go.mod 被
  意外連動升版
