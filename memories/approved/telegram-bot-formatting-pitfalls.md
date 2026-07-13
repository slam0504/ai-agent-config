---
status: approved
scope: global
applies_to: both
confidence: verified
verified_on: 2026-07-13
source: distill
reviewed_by: slam0504
---

# Telegram Bot 訊息格式化 pitfalls

Vendor contract（以 verified_on 當日的 Bot API 行為為準，未來使用前建議對
官方文件刷新：<https://core.telegram.org/bots/api#sendmessage>、
<https://core.telegram.org/bots/api#formatting-options>）：

- `sendMessage` text 上限 **4,096 字元**（以 entities parsing 後計）。若用 raw
  HTML 長度作切割依據，必須使用一致的字元計數單位並保留安全餘裕；不要把
  byte length、rune count 與 Telegram 的計數方式視為等價，且要涵蓋 emoji 測試
- `sendPhoto` caption 上限只有 **1,024 字元** —— 「文字改用圖片回傳」在字數
  帳上是反效果，除非把文字畫進圖片（代價：不可複製/搜尋、連結不可點、需
  字型渲染依賴）
- HTML parse mode 只接受固定 tag 白名單；不平衡或未知標籤可能讓 API 以
  HTTP 400 拒收整則訊息

實作 pattern（2026-07-13 於 arkham-docs-server PR #16–#19 實作並實機驗證，
零 400）：

1. **上游資料含 HTML 時一律淨化、不直通**。管線順序：
   `sanitize（br/hr → 換行、移除可辨識標籤）→ 必要時在安全邊界 truncate →
   escapeHTML → 最後才由 formatter 加上自己的標籤`。殘留的畸形標籤或
   `<>&` 必須由 escapeHTML 轉成純文字；順序錯置（先 truncate 再 sanitize）
   可能產生被切半的殘缺標籤。
2. **parse_mode 跟隨 formatter 實際產出的內容，不跟事件類型**。用
   `(text, parseMode)` 成對回傳；所有 fallback（parse 失敗、錯誤 body、
   raw dump）必須回純文字——未 escape 的內容絕不能掛 HTML mode 送出。
3. **超長訊息的切割在 formatter 產生 HTML 之後，沿標籤已閉合的結構邊界進行**
   （例如條目間空行、其次單行邊界；formatter 應保證標籤在單行內閉合）。
   rune 級硬切只保留給無標籤的純文字，且仍須替 API 的實際計數方式保留餘裕。
4. 名稱/標題類欄位 escape-only（字面角括號保留可見）；只有自由文字欄位走
   完整 sanitize。
