#!/usr/bin/env python3
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import textwrap
from datetime import datetime, timezone


def project_slug(project_dir: pathlib.Path) -> str:
    name = project_dir.name or "unknown"
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", name).strip("-") or "unknown"


def allow_stop() -> None:
    return


def block_stop(reason: str) -> None:
    print(
        json.dumps(
            {
                "decision": "block",
                "reason": reason[:4000],
            },
            ensure_ascii=False,
        )
    )


def run(cmd: list[str], cwd: pathlib.Path, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def first_decision_token(review_text: str) -> str:
    # Contract (see prompt below): "First non-empty line must be exactly one
    # of: APPROVE, REVISE, BLOCK" — not merely start with one of those words.
    for line in review_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        token = stripped.upper()
        if token in {"APPROVE", "REVISE", "BLOCK"}:
            return token
        break
    return ""


def main() -> int:
    raw_input = sys.stdin.read()
    try:
        hook_input = json.loads(raw_input or "{}")
    except json.JSONDecodeError:
        hook_input = {}

    project_dir = pathlib.Path(
        hook_input.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    ).resolve()

    artifacts_root = pathlib.Path(
        os.environ.get("CODEX_IMPLEMENTATION_REVIEW_DIR")
        or (pathlib.Path.home() / ".claude" / "hook-artifacts" / "codex-implementation-review")
    ).expanduser()
    out_dir = artifacts_root / project_slug(project_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    request_file = out_dir / "stop-request.json"
    request_file.write_text(raw_input, encoding="utf-8")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    review_file = out_dir / "implementation-review.md"
    log_file = out_dir / f"implementation-review-{timestamp}.log"
    state_file = out_dir / "state.json"

    try:
        state = json.loads(state_file.read_text(encoding="utf-8")) if state_file.exists() else {}
    except json.JSONDecodeError:
        state = {}

    git_check = run(["git", "rev-parse", "--is-inside-work-tree"], project_dir)
    if git_check.returncode != 0 or git_check.stdout.strip() != "true":
        allow_stop()
        return 0

    diff = run(["git", "diff", "--no-ext-diff", "--"], project_dir, timeout=60).stdout
    staged_diff = run(["git", "diff", "--cached", "--no-ext-diff", "--"], project_dir, timeout=60).stdout
    untracked = run(["git", "ls-files", "--others", "--exclude-standard"], project_dir, timeout=30).stdout

    review_input = "\n".join(
        [
            "UNSTAGED DIFF:",
            diff.strip(),
            "",
            "STAGED DIFF:",
            staged_diff.strip(),
            "",
            "UNTRACKED FILES:",
            untracked.strip(),
        ]
    ).strip()

    if not review_input.replace("UNSTAGED DIFF:", "").replace("STAGED DIFF:", "").replace("UNTRACKED FILES:", "").strip():
        allow_stop()
        return 0

    diff_hash = hashlib.sha256(review_input.encode("utf-8")).hexdigest()
    if state.get("approved_hash") == diff_hash:
        allow_stop()
        return 0

    if hook_input.get("stop_hook_active") and state.get("blocked_hash") == diff_hash:
        allow_stop()
        return 0

    codex_bin = os.environ.get("CODEX_BIN", "codex")
    if shutil.which(codex_bin) is None:
        block_stop(f"Codex implementation review could not run: {codex_bin!r} was not found.")
        return 0

    timeout_sec = int(
        os.environ.get("CODEX_IMPLEMENTATION_REVIEW_TIMEOUT")
        or os.environ.get("CODEX_REVIEW_TIMEOUT")
        or "180"
    )
    truncated_notice = ""
    max_diff_chars = int(os.environ.get("CODEX_IMPLEMENTATION_REVIEW_MAX_DIFF_CHARS", "120000"))
    prompt_diff = review_input
    if len(prompt_diff) > max_diff_chars:
        prompt_diff = prompt_diff[:max_diff_chars]
        truncated_notice = (
            f"\nThe diff content below was truncated at {max_diff_chars} characters. "
            "Run git diff commands yourself if more context is needed.\n"
        )

    transcript_path = hook_input.get("transcript_path") or hook_input.get("transcriptPath") or ""
    transcript_note = ""
    if transcript_path and pathlib.Path(transcript_path).exists():
        transcript_note = f"\nClaude transcript path: {transcript_path}\n"

    prompt = textwrap.dedent(
        f"""
        You are reviewing Claude Code's implementation before it stops.

        Goal:
        - Catch correctness bugs, behavioral regressions, missing tests, unsafe changes, and scope creep.
        - Do not edit files.
        - Review the diff and available repository context.

        Inputs:
        - Hook request JSON: {request_file}
        {transcript_note}
        Required response format:
        - First non-empty line must be exactly one of: APPROVE, REVISE, BLOCK
        - Then provide concise findings with file paths and evidence.

        Decision guidance:
        - APPROVE: no actionable implementation issues found; verification is adequate or remaining risk is explicitly acceptable.
        - REVISE: implementation is directionally okay but needs fixes, tests, clarification, or stronger verification.
        - BLOCK: change is dangerous, destructive, likely wrong, security-sensitive without safeguards, or risks data loss.

        Review standards:
        - Prioritize concrete bugs and missing verification over style preferences.
        - Do not invent issues. Every finding must cite evidence from the diff, existing code, tests, docs, or confirmed requirements.
        - If required context is missing, return REVISE and list the exact questions or evidence needed.
        - If approved, mention that user confirmation is still required before final acceptance.
        {truncated_notice}
        Current diff to review:
        ```diff
        {prompt_diff}
        ```
        """
    ).strip()

    cmd = [
        codex_bin,
        "exec",
        "-C",
        str(project_dir),
        "--sandbox",
        "read-only",
        "--output-last-message",
        str(review_file),
        "-",
    ]

    try:
        completed = subprocess.run(
            cmd,
            input=prompt,
            text=True,
            capture_output=True,
            timeout=timeout_sec,
            check=False,
        )
    except subprocess.TimeoutExpired:
        state["blocked_hash"] = diff_hash
        state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        block_stop(
            f"Codex implementation review timed out after {timeout_sec}s. "
            "Claude should report the timeout and ask the user whether to retry or continue manually."
        )
        return 0

    log_file.write_text(
        "COMMAND:\n"
        + " ".join(cmd)
        + "\n\nSTDOUT:\n"
        + completed.stdout
        + "\n\nSTDERR:\n"
        + completed.stderr,
        encoding="utf-8",
    )

    if review_file.exists():
        review_text = review_file.read_text(encoding="utf-8", errors="replace")
    else:
        review_text = (completed.stdout + "\n" + completed.stderr).strip()

    if completed.returncode != 0:
        state["blocked_hash"] = diff_hash
        state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        block_stop("Codex implementation review failed.\n\n" + review_text)
        return 0

    decision = first_decision_token(review_text)
    if decision == "APPROVE":
        state["approved_hash"] = diff_hash
        state.pop("blocked_hash", None)
        state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        allow_stop()
        return 0

    if decision in {"REVISE", "BLOCK"}:
        state["blocked_hash"] = diff_hash
        state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        block_stop(
            "Codex implementation review requires follow-up. Address the findings before stopping.\n\n"
            + review_text
        )
        return 0

    state["blocked_hash"] = diff_hash
    state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    block_stop(
        "Codex implementation review did not return APPROVE, REVISE, or BLOCK. "
        "Claude should inspect the review output and resolve the ambiguity before stopping.\n\n"
        + review_text
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
