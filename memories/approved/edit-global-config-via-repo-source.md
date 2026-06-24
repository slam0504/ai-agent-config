---
status: approved
scope: global
applies_to: both
confidence: verified
verified_on: 2026-06-24
source: distill
reviewed_by: slam0504
---

# 改全域 CLAUDE.md / AGENTS.md 要動 repo 源檔，不可直改 home

`ai-agent-config/install.sh` 用 `cp` 把 repo 的 `claude/CLAUDE.md`、
`codex/AGENTS.md`、`codex/config.toml` **覆蓋**到 `~/.claude/` 與 `~/.codex/`
對應位置(覆蓋前有 backup 到 `~/.ai-agent-config-backup/`)。

**Why：** 直接編輯 `~/.claude/CLAUDE.md` 或 `~/.codex/AGENTS.md` 的本機版本，
會在下次 `./install.sh` 被 repo 版本靜默蓋回，本機改動遺失(雖可從 backup 找回)。

**How to apply：**
- 全域規則 / 偏好的修改一律改 **repo 源檔**(`ai-agent-config/claude/CLAUDE.md`
  等)，再跑 `./install.sh` 落地。
- 改完可用 `diff ~/.claude/CLAUDE.md ai-agent-config/claude/CLAUDE.md` 確認 IN SYNC。
