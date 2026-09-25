---
name: commit-ready
description: Pre-commit readiness check for any project. Use when the user asks "is this ready to commit", "check before I commit", "/commit-ready", "最後檢查一下", or "pre-commit check". Detects project type (Go / Node / Python), runs lint + tests + type checks, scans staged changes for debug leftovers, TODOs, and potential secrets, then reports pass/fail with exact fix commands. Does NOT commit — user decides based on the report.
---

# Commit Ready Check

A final pre-commit gate that surfaces blockers before the user runs `git commit`. **Never creates a commit.** Only reports.

## Workflow

### 1. Detect project type
From the current working directory (or nearest ancestor with a manifest):

| File | Project type |
|---|---|
| `go.mod` | Go |
| `package.json` | Node / Vue / React |
| `pyproject.toml` / `requirements.txt` | Python |
| `Cargo.toml` | Rust |

If multiple, ask the user which one applies to the changes being committed.

### 2. Collect staged + unstaged changes
Run:
```
git status --short
git diff --stat
git diff --cached --stat
```
Show a one-line summary: `"X staged, Y unstaged, Z untracked"`. If nothing is staged and nothing is modified, report "no changes to commit" and stop.

### 3. Project-specific checks

Run the checks **in parallel where possible** (single message, multiple Bash calls) and collect results.

#### Go
- `go build -o /dev/null ./...` — compile all packages, no binary left behind
- Lint: prefer `make lint-fix` if Makefile has it; otherwise `golangci-lint run` if available; otherwise `go vet ./...`
- Tests: prefer `make test` if Makefile has it; otherwise `go test ./...`
- If project uses mockery: run `make test-gen` then `git diff --name-only -- '*/mocks/*'` — if non-empty, mocks are out of date

#### Node / Vue / React
From `package.json` scripts, run whichever exist (skip silently if missing):
- `npm run lint` (or `pnpm lint` / `yarn lint` — match the lockfile)
- `npm run type-check` (or `tsc --noEmit` if no script)
- `npm run test:unit` or `npm test`
- `npm run build` **only if the user asks for it** — usually too slow for a pre-commit check

#### Python
- `ruff check .` or `flake8` (whichever is configured)
- `mypy .` if configured
- `pytest` if a test dir exists

### 4. Code hygiene scans (all project types)

Scan **only the staged changes** (`git diff --cached`) for:

| Pattern | Flag as |
|---|---|
| `console.log`, `debugger`, `print(` in non-test files | Debug leftover |
| `TODO`, `FIXME`, `XXX` newly added | Unfinished work (warn, not block) |
| `fmt.Println`, `log.Println` newly added in Go (outside tests/main) | Debug leftover |
| Hardcoded URLs with credentials (`://user:pass@`) | Secret |
| AWS-style keys (`AKIA[0-9A-Z]{16}`), GCP service account JSON, private keys (`-----BEGIN`) | Secret |
| `.env`, `credentials.json`, `*.pem`, `*.key` in staged files | Secret file |
| Files over 1 MB | Large file warning |

Use `git diff --cached` + `grep` for the scan. **Never read the secrets aloud** — just flag the file and line.

### 5. Report

Format the report clearly. Use a checklist. Example:

```
Commit Ready Report
───────────────────
Project: Go (game-management-platform)
Staged: 4 files, 127 +/-

✓ Build passed          go build ./...
✓ Lint clean            make lint-fix
✗ Tests failing         make test
    → internal/platform-backoffice/usecase/imagereview/scan_test.go:42
      TestScanUseCase_Execute: expected 3 batches, got 0
✗ Mocks out of date     make test-gen produced diffs in:
    → internal/platform-backoffice/repository/mocks/image_review_repository.go
⚠ Debug leftover        fmt.Println in scan.go:88
⚠ New TODO              "TODO: handle 409" in handler.go:55

BLOCKERS (2):
  1. Fix failing test, then re-run
  2. Stage regenerated mocks:
       git add internal/platform-backoffice/repository/mocks

WARNINGS (2):
  • Remove fmt.Println or convert to structured log
  • Address or ticket the new TODO

Not ready to commit. Fix the 2 blockers above.
```

If everything passes:

```
✓ Commit Ready. You can run git commit now.
```

## Rules

- **Never run `git commit`** — only report.
- **Never stage or unstage files** — the user controls what goes into the commit.
- **Do not auto-fix** unless the user explicitly asks. `lint-fix` is acceptable because it's the idempotent fix command; anything that changes behaviour is off limits.
- **Do not touch files outside the working copy**.
- If a check command doesn't exist in the project, skip it and note `(skipped: no such target)` in the report — don't fail the whole run.
- Secrets scan is advisory; if a hit looks like a false positive (e.g. a test fixture), say so in the report but still surface it.
