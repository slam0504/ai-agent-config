---
name: distill
description: Use when the user explicitly invokes /distill or asks Claude to distill current work, review memory candidates, or promote durable context for cross-machine sync. Produces reviewed memory candidates from visible context, .remember/ notes, and project auto-memory; never syncs raw memory or writes approved memory without explicit user approval. Do not auto-trigger on ordinary summaries, handoffs, or reviews.
---

# Distill Memory Candidates

Turn useful working context into reviewed memory candidates. The goal is
controlled recall, not automatic raw memory sync. Default output is a proposal;
write files only after the user approves.

## Boundaries

- Never sync or treat `~/.claude/projects/*/memory/` raw files as a GitHub source.
- Never store secrets, credentials, full transcripts, or raw generated memory.
- Do not promote one-off task details. Keep short-term state in `.remember/`,
  the issue, PR, or project handoff.
- Do not implicitly upgrade ordinary summaries, handoffs, or reviews to memory.
- Write to `memories/review/` by default. Write to `memories/approved/` only
  when the user explicitly says the item is approved.

## Sources

Use the narrowest available sources:

1. Current visible conversation context.
2. Current project `.remember/` (`now.md`, `today-*.md`, `recent.md`) when present.
3. Current project `~/.claude/projects/<slug>/memory/` and its `MEMORY.md`.
4. Existing `ai-agent-config/memories/approved/` and `memories/review/` entries
   to detect duplicates or conflicts.

Do NOT scan the full session transcript; use only the visible context above. If
a full-transcript source is ever needed, ask the user for the path first.

If the `ai-agent-config` checkout is not obvious, look for
`~/playground/ai-agent-config`; if absent, ask for the path.

## Candidate Filter

Only propose a memory when it is likely to recur and improves future behavior.

Reject or leave in short-term notes when:

- It happened once and has no clear reuse value.
- The repo, git history, issue, PR, CLAUDE.md, or existing memory already records it.
- It is a guess with no evidence and no clear future check.
- It conflicts with existing approved memory and the replacement is not clear.

Upgrade threshold — distinguish facts from patterns:

- A **verified fact** (e.g. "bucket X is production") is eligible once confirmed;
  do not require repetition.
- A **pattern / convention / abstraction** follows Rule of Three:
  - First observation: keep as short-term context.
  - Second observation: list as a candidate, mark `confidence: assumed`.
  - Third confirmed observation: eligible for durable memory / a skill.

## Routing

| Signal | Destination |
|---|---|
| Cross-project preference or operating rule | `CLAUDE.md` proposal, or `memories/review/` with `scope: global`, `applies_to: both` or `claude` |
| Project-specific verified fact or convention | `~/.claude/projects/<slug>/memory/` (local), OR `memories/review/` with `scope: project` if cross-machine durable |
| Reusable workflow needing procedural steps | Propose a skill (point to skill-creator) instead of memory |
| Short-lived task state | Keep in `.remember/`, do not upgrade |

When writing to local project auto-memory, include in frontmatter:

```yaml
confidence: verified | assumed
verified_on: YYYY-MM-DD
```

A local project auto-memory write happens only after the user approves the
candidate, stays on this machine, and must never be synced into the repo.

## Review Format

Propose candidates before writing. For each candidate show:

- Title
- Proposed destination
- Scope (global / project / workflow)
- Applies to (claude / codex / both)
- Confidence (verified / assumed)
- verified_on (absolute date)
- Evidence (source files or conversation references)
- Why it is worth keeping
- Conflicts or duplicates (list them; let the user choose update or keep — do not blend a third version)

Each candidate must allow: **approve / edit / drop**. Unapproved items must not
enter `approved/`. If there are zero qualifying candidates, say so plainly — do
not invent filler.

When approved for cross-machine sync, write one Markdown file per candidate to
`memories/review/`:

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
approves the entry. The body must be concise, reusable, and traceable; include
evidence as short bullets or file references — never paste long transcripts.

## Audit (run alongside distill)

List current project memory entries whose `confidence: assumed` or whose
`verified_on` is old, and flag them for re-verification.

## Validation

Before reporting completion:

- Run a secret-pattern scan over any new or changed memory files.
- Check for duplicates against `memories/approved/` and `memories/review/`.
- Confirm no raw files from `~/.claude/projects/*/memory/` were copied into the repo.
- State whether files were only proposed, written to `review/`, or approved.
