---
name: commit-ready
description: Pre-commit readiness check for any project. Use when the user asks "is this ready to commit", "check before I commit", "/commit-ready", "最後檢查一下", or "pre-commit check". Detects project type (Go / Node / Python), runs read-only lint + tests + type checks (never modifies or generates files in the working tree), scans staged changes for debug leftovers, TODOs, and potential secrets, then reports pass/fail with exact fix commands. Does NOT commit — user decides based on the report.
---

# Commit Ready Check

A final pre-commit gate that surfaces blockers before the user runs `git commit`. **Never creates a commit. Never modifies or generates files in the working tree.** Only reports.

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

**Scope of the checks.** Build / lint / tests run against the **working tree**. If there are unstaged changes alongside staged ones (partial staging), the content that would be committed is not what was checked: say so explicitly in the report (`checks cover working tree; staged content differs in N files`) and do not claim the commit content passed.

### 3. Project-specific checks

Run the checks **in parallel where possible** (single message, multiple Bash calls) and collect results.

**Read-only rule for every command below.** Before running any target or script, read what it actually does: the Makefile target and the commands it calls, the `package.json` script line, the tool config (`.golangci.yml`, `eslint.config.*`, `pyproject.toml`). A command is safe to run in the working tree only if you confirmed it does not write files there: no `--fix` / `--write` / fixer modes, no code generators, no build outputs inside the tree. If you cannot confirm that, either run it in an isolated copy (see the mock-check procedure) or skip it and report `(skipped: <command> may modify files — <what you saw>)`. This applies to lint, test, type-check and build commands alike, in every language section.

#### Go
- `go build -o /dev/null ./...` — compile all packages, no binary left behind
- Lint: use a target confirmed **not** to modify files: `make lint` if the Makefile has it and it does not invoke a fixer; otherwise `golangci-lint run`; otherwise `go vet ./...`. Never run `make lint-fix`, `golangci-lint run --fix`, or any fixer mode. If the only lint target modifies files, report `(skipped: lint target modifies files)` with the reason.
- Tests: `make test` if the Makefile has it and the target only runs `go test` (no generators, no `-o` outputs into the tree); otherwise `go test ./...`. `go test` may write to the build cache, which is outside the tree and acceptable.
- Mock freshness (mockery): **not run by default** because `make test-gen` rewrites files. Only when the user or project asks for it, run the generator in an isolated copy and compare the copy's files **before vs after the generator** by content hash. Do not use git inside the copy: if the repo is a linked worktree, `cp -R` carries a `.git` pointer file and any `git add`/`commit` in the copy would rewrite the real worktree's HEAD. Hashing the whole copy also covers mocks at the repo root and nested paths, plus anything else the generator touches.
  1. `cp -R <repo> <tmp> && rm -rf <tmp>/.git` — exact working-tree copy, git detached.
  2. Baseline, with failures propagated (a missing `shasum` or an unreadable file must not silently produce a short or empty list):
     ```sh
     ( set -o pipefail; cd <tmp> && find . -type f -exec shasum -a 256 {} + | sort ) > <tmp>.before || echo "HASH-BEFORE FAILED"
     [ -s <tmp>.before ] || echo "HASH-BEFORE EMPTY"
     ```
  3. `(cd <tmp> && make test-gen); echo "gen exit=$?"` — a non-zero exit means the check is incomplete; if the generator needs `.git` to run, report `(skipped: generator requires git metadata)`.
  4. After: same command as step 2 into `<tmp>.after`, with the same failure and emptiness checks. Then `diff <tmp>.before <tmp>.after; echo "diff exit=$?"` — `0` identical, `1` differences (a path only in `.before` was deleted or modified; only in `.after` was added or modified), `>1` the comparison itself failed.
  5. Verdict rule: report **"mocks are fresh"** only when both hash runs succeeded with non-empty lists, the generator exited 0, and `diff` exited 0. Any failure (hash error, empty list, generator non-zero, `diff` exit `>1`) is reported as **"mock check incomplete: <which step, exit code>"**, never as fresh. On `diff` exit 1, list the changed paths and mark which are mocks and which are other generated files.
  6. Never regenerate in the real working tree. Remove `<tmp>` and the two hash files afterwards.

#### Node / Vue / React
Read the `scripts` block in `package.json` first; run a script only after confirming its command line is read-only (skip with reason otherwise, skip silently if the script is missing). Match the package manager to the lockfile (`npm` / `pnpm` / `yarn`).
- `lint`: run only if the script does **not** pass `--fix` / `--write` (e.g. `eslint .` is fine, `eslint --fix .` or `prettier --write` is not). If the only lint script fixes, run the underlying tool directly without the fix flag (`npx eslint .`), or report `(skipped: lint script modifies files)`.
- `type-check`, or `tsc --noEmit` if there is no script. `tsc` without `--noEmit` emits files: do not run it.
- `test:unit` or `test`: check for `--updateSnapshot` / `-u` or coverage output directories inside the tree; if present, run in an isolated copy or skip with reason.
- `build`: **only if the user asks for it**, and only in an isolated copy — build outputs land in the tree.

#### Python
- `ruff check .` (never `ruff check --fix` or `ruff format`) or `flake8`, whichever is configured
- `mypy .` if configured
- `pytest` if a test dir exists; if `pytest` config writes reports or coverage files into the tree, run in an isolated copy or skip with reason

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
✓ Lint clean            make lint
✗ Tests failing         make test
    → internal/platform-backoffice/usecase/imagereview/scan_test.go:42
      TestScanUseCase_Execute: expected 3 batches, got 0
✗ Mocks out of date     make test-gen (in temp copy) produced diffs in:
    → internal/platform-backoffice/repository/mocks/image_review_repository.go
⚠ Debug leftover        fmt.Println in scan.go:88
⚠ New TODO              "TODO: handle 409" in handler.go:55

BLOCKERS (2):
  1. Fix failing test, then re-run
  2. Regenerate mocks in your working tree and stage them:
       make test-gen && git add internal/platform-backoffice/repository/mocks

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
- **Do not auto-fix or generate files in the working tree**, even if the user asks for `lint-fix`: point them to the command instead. Generated-output checks (mocks, codegen) run only in a temporary copy.
- **State what was checked**: working tree vs staged content (see step 2). Never report "commit content passed" when unstaged changes exist.
- **Do not touch files outside the working copy**.
- If a check command doesn't exist in the project, skip it and note `(skipped: no such target)` in the report — don't fail the whole run.
- Secrets scan is advisory; if a hit looks like a false positive (e.g. a test fixture), say so in the report but still surface it.
