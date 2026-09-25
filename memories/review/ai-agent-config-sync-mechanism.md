---
status: review
scope: global
applies_to: both
confidence: verified
verified_on: 2026-09-25
source: distill
reviewed_by:
supersedes: memories/approved/ai-agent-config-sync-mechanism.md
---

# ai-agent-config 是跨機器 / 跨工具的 agent 設定與 memory 同步機制

`~/playground/ai-agent-config` repo 透過 `install.sh` 把 durable 設定與審核過的
memory 同步到本機 agent。memory 採三目錄 review → approved 閘門；設定則走
「改 repo 源檔 → Codex／人工審核 → install」，不直接改 home。

## 安裝目標與 drift guard 分流（2026-09-25 起）

`install.sh` 對每個目標套用兩種模式之一：

- **guard**（機器可能手改、需保護本機編輯）：dst 與 repo source 不同且無
  `--force` 時 skip 並提示。目標：`~/.codex/AGENTS.md`、`~/.codex/config.toml`
  （由 template + overlay 組裝後比對）、`~/.claude/CLAUDE.md`、
  `~/.agents/skills/distill/`、`~/.claude/skills/distill/`。
- **overwrite**（repo 單向權威、本機不該手改）：直接覆蓋，覆蓋前仍備份。目標：
  `memories/approved/` 兩端、`~/.claude/hooks/*.py|*.sh`（逐檔，`tests/` 不裝，
  本機獨有檔案保留）、`~/.claude/agents/*.md`（安裝時把 `/Users/example` 換成
  `$HOME`）、`~/.claude/scripts/gemini-bridge.sh`、`~/.claude/skills/commit-ready/`。
- 只有 `distill` skill 目錄受 guard；`commit-ready` 是 overwrite。不要把「skill」
  一概當成同一種模式。

## Claude settings.json 用合併，不覆蓋、不受 guard

`claude/merge-settings.py` 把 `claude/settings.json` 併入唯一的
`~/.claude/settings.json`：

- 受管 key（repo 檔裡除 `permissions`、`hooks` 外的所有 top-level key）由 repo 決定；
  dict 型（`enabledPlugins`、`extraKnownMarketplaces`）做淺層聯集、repo 勝、本機獨有保留。
- `permissions` 只寫 repo 有的 key（目前只有 `defaultMode`）；本機 `allow`、`deny`、
  `additionalDirectories` 一律不動。共用版刻意不含 `permissions.allow`，歷史授權
  留在 `claude/settings.local.example.json` 供逐項選用，不自動匯入。
- `hooks` 依事件與 matcher 合併：省略、`""`、`"*"` 視為同一 matcher；命令比對前把
  `$HOME`／`~` 展開成實際路徑並跨同 matcher 的所有 group 去重；只新增缺少的命令，
  本機獨有的 hook 與 matcher 文字不改。
- `env` 等本機獨有 top-level key 保留。結果與現況相同時不寫檔；寫檔時保留原權限，
  新檔與備份建立時為 0600，備份路徑衝突直接失敗。

## Codex config 組裝

`~/.codex/config.toml` = `codex/config.toml.template`（共用：模型、推理強度、
verbosity、子代理預設、features、plugins、marketplaces、Playwright MCP）+
gitignored `codex/config.local.toml`（機器專屬：專案信任、本機 MCP 執行檔、TUI 狀態）。
`codex/config.local.toml` 為選用。不存在時，安裝器只使用共用 template；需要機器專屬
設定時，再參考 `codex/config.local.toml.example` 建立 overlay。若目的檔已存在且與組裝
結果不同，未指定 `--force` 時會略過並提示 drift。

## memory 與 review 目錄

- `memories/review/`：distill 候選，不載入、不當跨機器權威。
- `memories/approved/`：人工核可後才裝到 `~/.claude/docs/memories/approved/` 與
  `~/.codex/docs/memories/approved/`。
- `claude/review/<date>/`、`codex/review/<date>/`：設定候選與審核紀錄；`install.sh`
  不讀。核可後檔案搬到正式位置，README 留作稽核紀錄。
- raw memory（`~/.claude/projects/*/memory/`、`~/.codex/memories/`、`.remember/`）
  絕不當同步來源。

## How to apply

- 改全域規則或 hooks：改 repo 源檔 → 跑測試（`test/test_install.sh`、
  `test/test_drift_guard.sh`、`python3 test/test_merge_settings.py`、
  `cd claude/hooks && python3 -m unittest discover -s tests`）→ 審核 → `./install.sh`。
- guarded 目標若本機已 drift，確認後才 `--force`；overwrite 目標與 settings 不需要。
- 見 [[edit-global-config-via-repo-source]]。

## 證據

- `install.sh` 第 124–161 行的目標清單與模式參數（2026-09-25，commit `e327416`）。
- `claude/merge-settings.py` 模組 docstring 與 `test/test_merge_settings.py`（22 案例）。
- `claude/review/2026-09-25/README.md`、`codex/review/2026-09-25/README.md` 審核紀錄。
