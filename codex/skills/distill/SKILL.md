---
name: distill
description: Use when the user explicitly invokes $distill or asks Codex to distill current work, review memory candidates, or promote durable context for cross-machine sync. Produces reviewed memory candidates from visible context, repo guidance, remember-style notes, and Codex generated memories; never syncs raw memory or writes approved memory without explicit user approval.
---

# Distill Memory Candidates

Use this skill to turn useful working context into reviewed memory candidates for
the `ai-agent-config` repo. The goal is controlled recall, not automatic raw
memory sync.

## Boundaries

- Never write to or sync `~/.codex/memories/`; treat it as generated state.
- Never store secrets, credentials, full transcripts, or raw generated memory.
- Do not promote one-off task details. Keep short-term state in the thread,
  issue, PR, or project handoff.
- Default output is a proposal. Write files only after the user approves.
- Write to `memories/review/` by default. Write to `memories/approved/` only
  when the user explicitly says the item is approved.

## Sources

Use the narrowest available sources:

1. Current visible thread context.
2. Repo and global guidance such as `AGENTS.md`.
3. Project handoff notes such as `.remember/` when present.
4. `~/.codex/memories/` only as read-only supporting context.
5. Existing `ai-agent-config/memories/approved/` and `memories/review/` entries
   to detect duplicates or conflicts.

If the `ai-agent-config` checkout is not obvious, look for
`~/playground/ai-agent-config`; if absent, ask for the path.

## Candidate Filter

Only propose a memory when it is likely to recur and improves future behavior.

Reject or leave in short-term notes when:

- It happened once and has no clear reuse value.
- The repo, git history, issue, PR, or `AGENTS.md` already records it.
- It is a guess with no evidence and no clear future check.
- It conflicts with existing approved memory and the replacement is not clear.

Apply a conservative recurrence rule:

- First observation: keep as short-term context.
- Second observation: list as a candidate, but mark `confidence: assumed`.
- Third confirmed observation: eligible for durable memory.

## Routing

Use this route for each candidate:

| Signal | Destination |
|---|---|
| Cross-project preference or operating rule | `memories/review/` with `scope: global` and `applies_to: both` or `codex` |
| Project-specific verified fact or convention | `memories/review/` with `scope: project` |
| Reusable workflow needing procedural steps | Propose a skill instead of memory |
| Short-lived task state | Keep out of memory |

## Review Format

Propose candidates before writing. Include:

- Title
- Proposed destination
- Scope
- Applies to
- Confidence
- Evidence
- Why it is worth keeping
- Conflicts or duplicates

When approved for file creation, write one Markdown file per candidate:

```yaml
---
status: review
scope: global | project
project: optional-project-slug
applies_to: codex | claude | both
confidence: verified | assumed
verified_on: YYYY-MM-DD
source: distill
reviewed_by:
---
```

Use `status: approved` and fill `reviewed_by` only when the user explicitly
approves the entry for durable sync.

The body should be concise, reusable, and traceable. Include evidence as short
bullets or file references; do not paste long transcripts.

## Validation

Before reporting completion:

- Run a secret-pattern scan over any new or changed memory files.
- Check for duplicates against `memories/approved/` and `memories/review/`.
- Confirm no raw files from `~/.codex/memories/` were copied.
- State whether files were only proposed, written to review, or approved.
