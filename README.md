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

## Memory Review Workflow

Use this flow whenever Claude or Codex finds context that may be worth keeping
across machines:

```text
working context
        -> distill
        -> memories/review/
        -> human review
        -> memories/approved/
        -> commit + push
        -> pull + ./install.sh on another machine
        -> agents read approved memory only
```

Claude and Codex use different trigger surfaces:

- Claude: invoke the Claude `distill` skill with `/distill`.
- Codex: invoke the Codex skill with `$distill`.

The directories have distinct meanings:

- `memories/review/`: proposed entries. These are not durable rules yet and
  must not be loaded automatically.
- `memories/approved/`: reviewed entries. These are the only memories intended
  for cross-machine sync and agent use.
- `memories/rejected/`: optional audit trail for rejected candidates.

Typical Codex flow:

1. Ask Codex to distill current work:

   ```text
   $distill What from this work should become long-term memory?
   ```

2. Review the proposed candidates. Approve, edit, or drop each item.
3. Approved-for-review candidates are written to `memories/review/`.
4. After final human approval, move the entry to `memories/approved/`.
5. Commit and push the approved memory.
6. On another machine, pull the repo and run `./install.sh`.

Do not sync raw memory sources directly:

- Do not sync `~/.codex/memories/`.
- Do not sync `~/.claude/projects/*/memory/`.
- Do not sync `.remember/`.
- Do not load `memories/review/` as durable context.

## Install

From a clone of this repo:

```sh
./install.sh
```

The script backs up existing destination files before copying.
