# AI Agent Config

Personal AI agent configuration for syncing durable rules and settings across machines.

## Contents

- `codex/AGENTS.md`: global Codex collaboration rules.
- `codex/config.toml`: Codex user-level configuration.
- `claude/CLAUDE.md`: global Claude Code collaboration rules.
- `memories/curated.md`: manually reviewed durable context.
- `install.sh`: copies these files into the local home directory with backups.

## Sync Policy

This repo is for reviewed, durable configuration only.

Do commit:

- Global agent instructions.
- Non-secret config.
- Reviewed project conventions.
- Curated memories that are safe to reuse across machines.

Do not commit:

- API keys, tokens, passwords, SSH keys, or credentials.
- Generated raw memory files from `~/.codex/memories/`.
- Thread transcripts or temporary task state.
- Machine-specific files unless they are intentionally portable.

## Install

From a clone of this repo:

```sh
./install.sh
```

The script backs up existing destination files before copying.

