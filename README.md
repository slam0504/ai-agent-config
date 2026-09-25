# AI Agent Config

Personal AI agent configuration for syncing durable rules and settings across machines.

## Contents

- `codex/AGENTS.md`: global Codex collaboration rules.
- `codex/config.toml.template`: portable Codex user-level configuration.
- `codex/review/`: pending configuration proposals; never installed automatically.
- `codex/skills/distill/SKILL.md`: Codex `$distill` workflow for reviewed memory candidates.
- `claude/CLAUDE.md`: global Claude Code collaboration rules.
- `claude/settings.json`: managed Claude Code settings (permissions.defaultMode,
  hooks, enabledPlugins, ...); merged into `~/.claude/settings.json` rather than
  overwriting it, since Claude Code only has one user-level settings file.
- `claude/settings.local.example.json`: example of machine-local settings
  (`env.PATH`, `permissions.allow`, machine-specific hooks) that stay out of
  the synced file; not installed.
- `claude/hooks/`: Codex review-gate and context-checkpoint hooks, installed
  per file into `~/.claude/hooks/`.
- `claude/agents/`: shared subagent definitions, installed into `~/.claude/agents/`.
- `claude/scripts/`: helper scripts (e.g. `gemini-bridge.sh`) referenced by hooks/agents.
- `claude/skills/commit-ready/`: pre-commit readiness check skill.
- `claude/merge-settings.py`: merges `claude/settings.json` into a local `~/.claude/settings.json`.
- `claude/review/`: Claude configuration review records; not installed
  automatically once approved candidates have been promoted to the formal
  locations above (`hooks/`, `agents/`, `scripts/`, `skills/`, `settings.json`).
  Current: [2026-09-25](claude/review/2026-09-25/README.md) (approved and promoted).
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

### Claude settings merge

`~/.claude/settings.json` is a single user-level file, so `install.sh` merges
`claude/settings.json` into it via `claude/merge-settings.py` instead of
overwriting it:

- Managed top-level keys (`language`, `effortLevel`, `enabledPlugins`, ...) are
  set from the repo; dict-valued keys like `enabledPlugins` are unioned so
  local-only entries survive.
- `permissions`: only `defaultMode` is set from the repo; `allow`, `deny`,
  `ask`, `additionalDirectories` and any other local permissions are left
  untouched.
- `hooks`: repo hook commands are merged into the matching local group (same
  event + matcher) or appended as a new group; local-only events, groups and
  commands (e.g. a Telegram Stop hook) are never removed or reordered.
- Any other local top-level key (e.g. `env`) is preserved as-is.

### Codex config

Review record: [2026-09-25 local Codex configuration](codex/review/2026-09-25/README.md) (approved and merged into the template).

`~/.codex/config.toml` is assembled from `codex/config.toml.template` (portable
settings) plus an optional, gitignored `codex/config.local.toml` (machine-specific
project paths and trust). Copy `codex/config.local.toml.example` to
`codex/config.local.toml` on each machine; absolute paths and trust state are never
synced across machines.

### Drift guard

If a destination already exists and differs from the repo source, `install.sh`
skips it and reports the drift instead of silently overwriting (it may hold
un-synced local edits). The canonical fix is to edit the **repo source** and
re-run. To overwrite anyway (a backup is still taken):

```sh
./install.sh --force
```

The guard applies to machine-editable targets (`CLAUDE.md`, `AGENTS.md`,
`config.toml`). Repo-authoritative targets the machine should never hand-edit —
`memories/approved/`, `claude/hooks/`, `claude/agents/`, `claude/scripts/`,
`claude/skills/commit-ready/` — are exempt and overwritten directly, so
routine updates don't require `--force`. `claude/settings.json` doesn't use
the guard either; it goes through the JSON merge described above instead.
