---
status: approved
scope: global
applies_to: both
confidence: verified
verified_on: 2026-06-24
source: distill
reviewed_by: slam0504
---

# ai-agent-config 是跨機器 / 跨工具的 agent 設定與 memory 同步機制

`~/playground/ai-agent-config` repo 透過 `install.sh` 把 durable 設定與審核過的
memory 同步到本機 agent。memory 採三目錄 review → approved 閘門。

- `memories/review/`：distill 產生的候選，**不載入**為 durable context、不跨機器當權威。
- `memories/approved/`：人工審核通過，`install.sh` 才會裝到
  `~/.claude/docs/memories/approved/`(Claude)與 `~/.codex/docs/memories/approved/`(Codex)。
- `memories/rejected/`：可選稽核紀錄。
- raw memory(`~/.claude/projects/*/memory/`、`~/.codex/memories/`、`.remember/`)
  是本機 generated state，**絕不**當 GitHub 同步來源。

**How to apply：** 要新增跨機器 durable memory 時，用 distill 產生候選 → 寫
`memories/review/` → 人工 approve 後移 `memories/approved/` → commit/push →
另一台機器 pull + `./install.sh`。
