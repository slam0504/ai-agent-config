#!/usr/bin/env python3
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import textwrap
from datetime import datetime, timezone


def hook_response(decision: str, reason: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": decision,
                    "permissionDecisionReason": reason[:4000],
                }
            },
            ensure_ascii=False,
        )
    )


def project_slug(project_dir: pathlib.Path) -> str:
    name = project_dir.name or "unknown"
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", name).strip("-") or "unknown"


QUOTA_PATTERN = re.compile(r"usage limit|rate[ -]?limit|429", re.IGNORECASE)


def parse_decision(review_text: str) -> str:
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


def respond_with_verdict(engine: str, review_text: str, review_file: pathlib.Path) -> None:
    decision = parse_decision(review_text)
    if decision == "APPROVE":
        hook_response(
            "ask",
            f"{engine} approved Claude's plan. User confirmation is still required.\n\n"
            f"Review file: {review_file}\n\n{review_text}",
        )
    elif decision in {"REVISE", "BLOCK"}:
        hook_response("deny", f"[{engine} review]\n\n{review_text}")
    else:
        hook_response(
            "deny",
            f"{engine} review did not return APPROVE, REVISE, or BLOCK. Stay in Plan Mode.\n\n"
            + review_text,
        )


def run_claude_fallback(
    prompt: str,
    project_dir: pathlib.Path,
    review_file: pathlib.Path,
    log_file: pathlib.Path,
    timeout_sec: int,
    extra_dirs: tuple[str, ...] = (),
) -> None:
    claude_bin = shutil.which(os.environ.get("CLAUDE_PLAN_REVIEW_CLAUDE_BIN", "claude"))
    if claude_bin is None:
        hook_response(
            "deny",
            "Codex hit its usage limit and 'claude' was not found for fallback review. "
            "Stay in Plan Mode.",
        )
        return

    cmd = [claude_bin, "-p", "--allowedTools", "Read,Glob,Grep"]
    for d in extra_dirs:
        cmd += ["--add-dir", d]
    model = os.environ.get("CLAUDE_PLAN_REVIEW_MODEL", "")
    if model:
        cmd += ["--model", model]

    try:
        completed = subprocess.run(
            cmd,
            input=prompt,
            text=True,
            capture_output=True,
            timeout=timeout_sec,
            check=False,
            cwd=str(project_dir),
        )
    except subprocess.TimeoutExpired:
        hook_response(
            "deny",
            f"Codex hit its usage limit; Claude fallback review timed out after "
            f"{timeout_sec}s. Stay in Plan Mode.",
        )
        return

    with log_file.open("a", encoding="utf-8") as f:
        f.write(
            "\n\n=== CLAUDE FALLBACK ===\nCOMMAND:\n"
            + " ".join(cmd)
            + "\n\nSTDOUT:\n"
            + completed.stdout
            + "\n\nSTDERR:\n"
            + completed.stderr
        )

    review_text = completed.stdout.strip()
    if completed.returncode != 0 or not review_text:
        hook_response(
            "deny",
            "Codex hit its usage limit and the Claude fallback review also failed. "
            "Stay in Plan Mode.\n\n" + (review_text or completed.stderr.strip()),
        )
        return

    review_file.write_text(review_text, encoding="utf-8")
    respond_with_verdict("Claude (fallback, Codex quota exhausted)", review_text, review_file)


def main() -> int:
    project_dir = pathlib.Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()).resolve()

    artifacts_root = pathlib.Path(
        os.environ.get("CODEX_PLAN_REVIEW_DIR")
        or (pathlib.Path.home() / ".claude" / "hook-artifacts" / "codex-plan-review")
    ).expanduser()
    out_dir = artifacts_root / project_slug(project_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    raw_input = sys.stdin.read()
    request_file = out_dir / "exit-plan-request.json"
    request_file.write_text(raw_input, encoding="utf-8")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    review_file = out_dir / "plan-review.md"
    log_file = out_dir / f"plan-review-{timestamp}.log"

    try:
        hook_input = json.loads(raw_input or "{}")
    except json.JSONDecodeError:
        hook_input = {}

    transcript_path = hook_input.get("transcript_path") or hook_input.get("transcriptPath") or ""
    transcript_note = ""
    if transcript_path and pathlib.Path(transcript_path).exists():
        transcript_note = f"\nClaude transcript path: {transcript_path}\n"

    codex_bin = os.environ.get("CODEX_BIN", "codex")
    resolved_codex = shutil.which(codex_bin)
    if resolved_codex is None and pathlib.Path("/usr/local/bin/codex").exists():
        resolved_codex = "/usr/local/bin/codex"
    if resolved_codex is None:
        hook_response(
            "deny",
            f"Codex review could not run: {codex_bin!r} was not found. Stay in Plan Mode.",
        )
        return 0

    timeout_sec = int(os.environ.get("CODEX_PLAN_REVIEW_TIMEOUT", "300"))
    prompt = textwrap.dedent(
        f"""
        You are reviewing Claude Code's plan before it exits Plan Mode.

        Review posture:
        - Treat this as a code-review / design-review task, not just an execution
          safety gate.
        - Lead with bugs, public API risks, behavioral regressions, and missing
          tests.
        - Be skeptical of plans that are "specific enough to execute" but still
          leave contract ambiguity or maintainability risk.
        - Do not edit files.
        - Review only the plan and available repository context.

        Inputs:
        - Hook request JSON: {request_file}
        {transcript_note}
        Required response format:
        - First non-empty line must be exactly one of: APPROVE, REVISE, BLOCK
        - Then provide concise reasons.

        Decision guidance:
        - APPROVE: no material findings. The plan is specific, safe, scoped,
          and has verification tied to its stated acceptance criteria.
        - REVISE: the direction is acceptable, but the plan has actionable
          findings, unclear contract choices, weak tests, scope drift, or risk
          handling gaps.
        - BLOCK: the plan is dangerous, destructive, likely to damage unrelated
          work, or attempts to bypass review.

        Review checklist:
        - For public API / contract plans, review proposed code snippets as API.
          Check exported mutable globals, sentinel error matching, context value
          mutability, nil/zero-value behavior, concurrency expectations, backward
          compatibility, and adapter mapping assumptions.
        - For error-handling plans, verify errors.Is/errors.As behavior, coded
          error mapping, and whether transport adapters can translate failures
          without string matching.
        - For context-helper plans, check whether stored values contain mutable
          slices/maps/pointers and whether copy/immutability behavior is specified.
        - For verification, require tests that prove the plan's stated intent.
          Tests that are optional but cover a named acceptance criterion should be
          required.
        - If the plan lacks required context, assumptions, test data, environment
          details, dependency/version information, acceptance criteria, or a user
          decision, return REVISE.

        Return REVISE for any material public API mutability issue, contract
        ambiguity, adapter-mapping uncertainty, or missing intent-level test.
        Do not return APPROVE when meaningful unknowns remain.

        For REVISE or BLOCK, prefer this structure:
        - Findings:
        - Open questions:
        - Required plan changes:

        If approved, mention that user confirmation is still required before execution.
        """
    ).strip()

    cmd = [
        resolved_codex,
        "exec",
        "-C",
        str(project_dir),
        "--sandbox",
        "read-only",
        "--skip-git-repo-check",
        "--output-last-message",
        str(review_file),
        "-",
    ]

    # Remove the previous run's review so a failed run can't replay stale findings.
    review_file.unlink(missing_ok=True)

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
        hook_response(
            "deny",
            f"Codex review timed out after {timeout_sec}s. Stay in Plan Mode.",
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
        if QUOTA_PATTERN.search(completed.stdout + "\n" + completed.stderr):
            extra_dirs = [str(out_dir)]
            if transcript_path:
                extra_dirs.append(str(pathlib.Path(transcript_path).parent))
            run_claude_fallback(
                prompt, project_dir, review_file, log_file, timeout_sec, tuple(extra_dirs)
            )
            return 0
        hook_response(
            "deny",
            "Codex review failed. Stay in Plan Mode.\n\n" + review_text,
        )
        return 0

    respond_with_verdict("Codex", review_text, review_file)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
