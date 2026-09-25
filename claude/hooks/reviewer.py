"""Out-of-band reviewer CLI: prepare (lazy packet, full diff) + finalize. Human-gated."""
import argparse
import os
import sys

import review_loop_common as c


def _packet_path(root, n):
    return os.path.join(c.rl_dir(root), "iterations", f"{n:03d}-packet.md")


def _packet_meta_path(root, n):
    return os.path.join(c.rl_dir(root), "iterations", f"{n:03d}-packet.json")


def _feedback_archive(root, n):
    return os.path.join(c.rl_dir(root), "iterations", f"{n:03d}-feedback.md")


def build_packet(root, snapshot):
    """snapshot must be a review_loop_common.worktree_snapshot(root) result.

    The untracked-file section is built entirely from that snapshot — no
    second scan here — so the packet can never disagree with the
    completeness status a caller (cmd_prepare) derived from the same
    snapshot. Everything else (checkpoint, tracked-file diffs) is read
    fresh; those aren't subject to the untracked-content cap this snapshot
    exists for.
    """
    parts = []
    cp = os.path.join(root, ".agent", "session-checkpoint.md")
    if os.path.exists(cp):
        with open(cp) as f:
            parts.append("## Current Goal / Checkpoint\n\n" + f.read())
    parts.append("## git status --short\n\n```\n" + c.run_git(root, ["status", "--short"])[1] + "\n```")
    # Staged and unstaged shown separately: `git diff HEAD` alone hides a
    # change that is staged but reverted in the worktree, while the
    # fingerprint (which includes the cached diff) still counts it.
    parts.append("## git diff --cached --stat (staged)\n\n```\n" + c.run_git(root, ["diff", "--cached", "--stat", "HEAD"])[1] + "\n```")
    parts.append("## git diff --stat (unstaged)\n\n```\n" + c.run_git(root, ["diff", "--stat"])[1] + "\n```")
    parts.append("## git diff --cached (staged, full)\n\n```diff\n" + c.run_git(root, ["diff", "--cached", "HEAD"])[1] + "\n```")
    parts.append("## git diff (unstaged, full)\n\n```diff\n" + c.run_git(root, ["diff"])[1] + "\n```")
    untracked = snapshot["untracked"]
    if untracked:
        status = snapshot["status"]
        contents = snapshot["contents"]
        skip = set(status["over_limit"]) | set(status["unread"]) | set(status["unreadable"])
        if not status["complete"]:
            file_limit, total_limit = c.current_untracked_limits()
            lines = [f"- {rel}: over per-file limit ({file_limit} bytes)"
                     for rel in status["over_limit"]]
            lines += [f"- {rel}: unread (total limit {total_limit} bytes exceeded)"
                      for rel in status["unread"]]
            lines += [f"- {rel}: unreadable (see review-loop log)"
                      for rel in status["unreadable"]]
            parts.insert(0, "## REVIEW INCOMPLETE: untracked content over limit\n\n"
                             f"Per-file limit: {file_limit} bytes; total limit: {total_limit} bytes. "
                             "Content below does not cover these untracked files:\n\n"
                             + "\n".join(lines))
        sections = []
        for rel in sorted(untracked):
            if rel in skip:
                continue
            data = contents.get(rel)
            content = data.decode("utf-8", "replace") if data is not None else f"<unreadable: {rel}>"
            sections.append(f"### {rel}\n\n```\n{content}\n```")
        if sections:
            parts.append("## Untracked files (full content)\n\n" + "\n\n".join(sections))
    return "\n\n".join(parts) + "\n"


def cmd_prepare(root):
    pending = c.read_json(os.path.join(c.rl_dir(root), "pending.json"), {})
    if pending.get("status") != "pending":
        print("review-loop: no pending review", file=sys.stderr)
        return 1
    n = c.read_state(root).get("iteration", 0) + 1
    path = _packet_path(root, n)
    # `iteration` only advances in finalize, so a second prepare in the same
    # round would overwrite this iteration's packet + metadata and let a
    # review of the old tree be stamped onto the new one. Refuse instead.
    meta_path = _packet_meta_path(root, n)
    if os.path.exists(meta_path):
        print(f"review-loop: iteration {n} already has an unfinalized packet ({path}); "
              "finalize it before preparing again", file=sys.stderr)
        return 1
    # Compute the fingerprint right when the packet is built, and persist it
    # next to the packet — pending.json can be overwritten by a later Stop
    # before this review is finalized, so it is not a safe source of truth
    # for "which tree did this packet describe". The fp, the completeness
    # status written to metadata, and the packet body itself all come from
    # ONE worktree_snapshot() call — a second, independent scan (as this
    # used to do via build_packet() rescanning) could observe a different
    # tree if a file changes in between, so the metadata could say
    # complete=true while the packet it describes actually shows REVIEW
    # INCOMPLETE (or vice versa), and finalize --verdict pass would trust
    # the wrong one.
    snapshot = c.worktree_snapshot(root)
    status = snapshot["status"]
    c.atomic_write(path, build_packet(root, snapshot))
    c.write_json(meta_path, {
        "cheap_worktree_fp": snapshot["fp"],
        "base_sha": c.base_sha(root),
        "created_at": c.now_iso(),
        "complete": status["complete"],
        "over_limit": status["over_limit"],
        "unread": status["unread"],
        "unreadable": status["unreadable"],
    })
    print(path)
    return 0


def cmd_finalize(root, raw_path, verdict, new_findings):
    state = c.read_state(root)
    n = state.get("iteration", 0) + 1

    # The fingerprint/base_sha that describe the tree this packet was built
    # from live only in the per-packet metadata written by `prepare`.
    # pending.json is not safe here: a later Stop can rewrite it (for a
    # newer, different tree) before this review is finalized.
    meta = c.read_json(_packet_meta_path(root, n), {})
    if not meta.get("cheap_worktree_fp"):
        print(f"review-loop: missing packet metadata for iteration {n}; "
              "run 'prepare' before 'finalize'", file=sys.stderr)
        return 1
    reviewed_fp = meta["cheap_worktree_fp"]
    review_base_sha = meta.get("base_sha", "none")

    # "complete" is only present in metadata written by the fixed cmd_prepare
    # above; older metadata (or metadata hand-crafted without the key) has no
    # such field. Treat that as incomplete-unknown rather than assuming the
    # packet was complete — fail closed. A packet whose untracked content
    # wasn't fully read must never be finalized as a passing review: nothing
    # after this point would notice, because an over-limit file's fp doesn't
    # change on a same-size content edit, so the tree would never re-enqueue
    # and SessionStart would report idle forever.
    complete = meta.get("complete")
    incomplete = complete is not True
    if incomplete and verdict == "pass":
        if complete is None:
            print(f"review-loop: iteration {n} packet metadata predates the "
                  "untracked-content completeness check (no 'complete' key); "
                  "re-run 'prepare' before finalizing with verdict=pass",
                  file=sys.stderr)
        else:
            named = meta.get("over_limit", []) + meta.get("unread", []) + meta.get("unreadable", [])
            print(f"review-loop: iteration {n} packet was INCOMPLETE (untracked "
                  f"content not fully read: {', '.join(named) or 'unknown files'}); "
                  "cannot finalize with verdict=pass", file=sys.stderr)
        return 1

    with open(raw_path) as f:
        body = f.read().strip()
    packet_content = ""
    ppath = _packet_path(root, n)
    if os.path.exists(ppath):
        with open(ppath) as f:
            packet_content = f.read()
    pending_path = os.path.join(c.rl_dir(root), "pending.json")
    pending = c.read_json(pending_path, {})
    header_lines = [
        "---",
        f"review_base_sha: {review_base_sha}",
        f"reviewed_worktree_fp: {reviewed_fp}",
        f"review_packet_hash: {c.sha12(packet_content)}",
        f"iteration: {n}",
        f"verdict: {verdict}",
        f"new_findings: {'true' if new_findings else 'false'}",
    ]
    if incomplete:
        header_lines.append("review_incomplete: true")
    header_lines.append(f"created_at: {c.now_iso()}")
    header = "\n".join(header_lines) + "\n---\n\n"
    feedback = header + body + "\n"
    c.atomic_write(_feedback_archive(root, n), feedback)
    c.atomic_write(os.path.join(c.rl_dir(root), "codex-feedback.md"), feedback)

    done = (verdict == "pass") or (n >= state.get("max_iterations", 5)) or (not new_findings)
    # An incomplete review must never close the loop: the untracked content
    # it couldn't read was never actually reviewed, so the round can't be
    # done regardless of iteration count or new_findings.
    if incomplete:
        done = False
    state.update({"iteration": n, "last_verdict": verdict, "done": done})
    c.write_state(root, state)

    # Only mark pending.json reviewed if it still describes the tree this
    # packet was built from; a later Stop may have replaced it with a newer
    # tree that has not been reviewed yet and must stay pending.
    if pending.get("cheap_worktree_fp") == reviewed_fp:
        pending["status"] = "reviewed"
        c.write_json(pending_path, pending)
    else:
        c.log(root, f"finalize iter={n}: pending.json describes a newer tree; left pending")
    c.log(root, f"finalize iter={n} verdict={verdict} done={done} incomplete={incomplete}")
    print(f"review-loop: finalized iteration {n} (verdict={verdict}, done={done})")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="review-loop")
    p.add_argument("--root", default=None)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("prepare")
    f = sub.add_parser("finalize")
    f.add_argument("raw_path")
    f.add_argument("--verdict", choices=["pass", "needs_changes", "blocked"], default="needs_changes")
    f.add_argument("--new-findings", choices=["true", "false"], default="true")
    args = p.parse_args(argv)
    root = args.root or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    if args.cmd == "prepare":
        return cmd_prepare(root)
    return cmd_finalize(root, args.raw_path, args.verdict, args.new_findings == "true")


if __name__ == "__main__":
    sys.exit(main())
