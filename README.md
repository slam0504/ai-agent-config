# AI Agent Config

Personal AI agent configuration for syncing durable rules and settings across machines.

## Contents

- `codex/AGENTS.md`: global Codex collaboration rules.
- `codex/config.toml`: Codex user-level configuration.
- `codex/skills/distill/SKILL.md`: Codex `$distill` workflow for reviewed memory candidates.
- `claude/CLAUDE.md`: global Claude Code collaboration rules.
- `memories/review/`: proposed memory entries that are not loaded by agents.
- `memories/approved/`: reviewed memory entries that can be synced across machines.
- `memories/rejected/`: rejected candidates kept only when useful for audit.
- `install.sh`: copies these files into the local home directory with backups.

## Sync Policy

This repo is for reviewed, durable configuration only.

Do commit:

- Global agent instructions.
- Non-secret config.
- Reviewed project conventions.
- Approved memories that are safe to reuse across machines.

Do not commit:

- API keys, tokens, passwords, SSH keys, or credentials.
- Generated raw memory files from `~/.codex/memories/`.
- Thread transcripts or temporary task state.
- Machine-specific files unless they are intentionally portable.

For Codex, only `memories/approved/` is installed for agent use.
`memories/review/` stays as a review queue and must not be loaded as durable
context.

## Install

From a clone of this repo:

```sh
./install.sh
```

The script backs up existing destination files before copying.
