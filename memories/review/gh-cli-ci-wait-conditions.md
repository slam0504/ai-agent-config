---
status: review
scope: global
applies_to: both
confidence: assumed
verified_on: 2026-07-13
source: distill
reviewed_by:
---

# gh CLI 自動 merge 前的 CI 等待條件

PR 剛建立時 `gh pr checks` 會回「no checks reported」——此時以
「grep 不到 pending 就繼續」作為等待條件，會在 CI 還沒註冊任何 check 前
搶跑 merge。

**正確的等待條件必須同時滿足三項**：

1. 預期的 check set 在 deadline 前出現且數量 > 0；逾時仍沒有 check 要 fail
   loud，不能視為通過
2. 無 pending（全部跑完）
3. 所有 required／預期 checks 都是 pass；`fail`、`cancel` 必須阻擋，
   `skipping` 是否可接受要由 repo policy 明訂（若沒有 branch protection，
   `gh pr merge` 不會替你擋失敗的非 required check）

實作上可先用 `gh pr checks <n> --json name,bucket` 等待預期 checks 註冊，再用
`gh pr checks <n> --watch --fail-fast` 等它們完成；有 branch protection 時可加
`--required` 限定 required checks。`gh run watch <run-id> --exit-status` 只證明
單一 workflow run 的結果，不能取代 PR 層級的完整 check-set 判斷。

**Evidence（2026-07-13, arkham-docs-server PR）**：until-loop 只判
「pending 計數為 0」，在「no checks reported」窗口直接通過並 merge；
事後 main 上的 CI run 為 success、無實害，但屬真實流程漏洞。

單次踩雷 + 推理補強（第三項未實際踩過），故 confidence: assumed。
