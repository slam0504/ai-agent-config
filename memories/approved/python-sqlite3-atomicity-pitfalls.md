---
status: approved
scope: global
applies_to: both
confidence: verified
verified_on: 2026-07-13
source: distill
reviewed_by: slam0504
---

# Python sqlite3 原子性 pitfalls

兩個容易讓「看似一體」的 drop→rebuild→insert 序列失去原子性的行為：

1. 在預設的 **`LEGACY_TRANSACTION_CONTROL`** 下，若已有 pending transaction，
   `executescript()` 會先 commit 再執行腳本內容。把它放進你以為的 transaction
   裡，rollback 保證會被破壞；需要在同一 transaction 內建表時，把 schema
   拆成 statement list 逐句 `execute()`。
2. 在 legacy handling 下，Python sqlite3 不會因 DDL 自動開 transaction
   （隱式 BEGIN 只對 DML 生效）。未被明確 transaction 包住的 DROP/CREATE
   會立即持久化；若後續 insert 失敗，舊資料已經沒了，留下空表。

Python 3.12+ 建議透過 `Connection.autocommit` 控制 transaction；
`isolation_level` 只有在 `autocommit=LEGACY_TRANSACTION_CONTROL` 時有效。使用前
應先確認連線採用的模式，不要把不同 transaction mode 的行為混為一談。參考：
<https://docs.python.org/3/library/sqlite3.html#transaction-control>。

**原子重建的兩個正確做法**：

- 在 legacy mode 設 `isolation_level=None`，再明確 `BEGIN IMMEDIATE`、逐句
  `execute()`，成功時 `COMMIT`、失敗時 `ROLLBACK`。SQLite 的 DDL 可以
  rollback，失敗時被 drop 的表會完整復原。
- 或整個 build 寫到與目的檔相同 filesystem 的 temporary DB，關閉相關連線且
  全部成功後再以 `os.replace()` 原子換檔。

**Evidence（2026-07-13, arkham-lcg-mcp-server）**：`--cards-only` refresh
原實作在 live db 上 drop+recreate 後 insert，peer 實測 insert 失敗後
`old_card_after_failure=0`（舊資料遺失）；修正 commit `e17e12d` 採
BEGIN IMMEDIATE 方案 + in-txn 筆數 sanity check，配套 fixture db 測試證明
失敗時舊資料保留。
