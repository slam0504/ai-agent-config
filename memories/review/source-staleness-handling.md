---
status: review
scope: global
applies_to: both
confidence: assumed
verified_on: 2026-07-08
source: distill
reviewed_by:
---

# 官方文件標舊版本或與實測衝突時的採信規則

來源可信度排序（官方優先）的**補充條件，不是推翻官方優先原則**：

> 當官方文件明確標示舊版本、或與目前實測／活躍維護專案行為衝突時，不能只依來源階層採信官方文字；應標註版本差異、保留不確定性，並以當前 artifact 或實測決定。

## 觀察紀錄（Rule of Three：目前兩次，第三次確認後可升級）

兩次皆於 2026-07-06、stellaris-mods 專案：

1. 官方 wiki（頁面驗證於遊戲 3.7 版）稱 `web_link` 開啟「integrated web browser」→ 實際該內建瀏覽器多版本前已移除，現開 Steam Overlay browser（活躍專案 Stellaris Dashboard 的 Workshop 留言證實）。誤信 wiki 會讓核心功能綁在不存在的機制上。
2. 官方 wiki 稱 ironman 存檔「encrypted and cannot be edited」→ 活躍專案 Dashboard README 明載支援 Ironman 讀取。處理：spec 不預先承諾也不預先排除，標註來源衝突、留待實測。

## 適用時的動作

- 標註「來源驗證版本 vs 當前版本」的落差
- 衝突雙方都寫進文件，不挑方便的一方
- 結論措辭降級為「待實測」，由當前 artifact（實際檔案／執行行為）裁決
