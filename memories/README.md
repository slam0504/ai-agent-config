# Reviewed Memory Workflow

This directory stores memory entries that are safe to review and sync across
machines. Generated raw memory stays outside this repo.

## Directories

- `review/`: proposed entries. Agents must not load these as durable context.
- `approved/`: reviewed entries. `install.sh` copies these for local agent use.
- `rejected/`: rejected entries kept only when an audit trail is useful.

## Approval Rules

An approved memory must be:

- Free of secrets, credentials, raw transcripts, and private tokens.
- Reusable beyond the current one-off task.
- Scoped correctly as `global` or `project`.
- Marked with `confidence` and `verified_on`.
- Checked against existing approved memory for conflicts.

## Frontmatter

```yaml
---
status: approved
scope: global | project
project: optional-project-slug
applies_to: codex | claude | both
confidence: verified | assumed
verified_on: YYYY-MM-DD
source: distill
reviewed_by: slam0504
---
```
