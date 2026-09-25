"""P7: an incomplete review must never be finalized as a passing review, and
the untracked-content cap must actually bound what gets read (not just what
gets reported).

D1: reviewer.cmd_prepare persists untracked-content completeness into packet
    metadata (computed from the SAME scan as the fp); cmd_finalize refuses
    verdict=pass when that metadata says incomplete (or is missing the key
    entirely — old-format metadata fails closed, not open), and an allowed
    non-pass finalize on an incomplete packet stamps `review_incomplete: true`
    and must never mark the round done.
D2: a read/stat failure (e.g. permission denied) must also make
    untracked_status()["complete"] False, not just over-limit/unread files.
D3: the cap must bound the actual bytes read, not just react to os.stat's
    reported size — a file that is bigger than it appears (stat lies, or a
    file that's merely far over the *remaining total* budget) must be caught
    by the bounded read itself and never be fully hashed.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import review_loop_common as c  # noqa: E402
import reviewer  # noqa: E402
import stop_enqueue  # noqa: E402


def git(repo, *args):
    subprocess.run(
        ["git", "-C", repo, "-c", "user.email=t@t", "-c", "user.name=t", *args],
        check=True, capture_output=True, text=True,
    )


def write_bytes(repo, rel, data):
    with open(os.path.join(repo, rel), "wb") as f:
        f.write(data)


def enable_review_loop(repo):
    d = c.rl_dir(repo)
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "enabled"), "w").close()


def write_raw(repo, text="looks good"):
    path = os.path.join(repo, "raw-feedback.txt")
    with open(path, "w") as f:
        f.write(text)
    return path


class _RepoCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = self.tmp.name
        git(self.repo, "init", "-q")
        git(self.repo, "commit", "-q", "--allow-empty", "-m", "init")
        enable_review_loop(self.repo)

    def tearDown(self):
        self.tmp.cleanup()

    def _stop(self):
        stop_enqueue.run(json.dumps({"cwd": self.repo}))


class TestFinalizeRefusesIncompletePass(_RepoCase):
    """D1(a)/(b): prepare over the cap, then try to finalize as pass."""

    def setUp(self):
        super().setUp()
        self.env = patch.dict(os.environ, {
            "RL_UNTRACKED_FILE_LIMIT": "10",
            "RL_UNTRACKED_TOTAL_LIMIT": "1000",
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        write_bytes(self.repo, "big.txt", b"X" * 50)  # over the 10-byte file limit
        self._stop()
        self.assertEqual(reviewer.cmd_prepare(self.repo), 0)
        meta_path = os.path.join(c.rl_dir(self.repo), "iterations", "001-packet.json")
        self.meta = c.read_json(meta_path, {})

    def test_prepare_persists_incomplete_status(self):
        self.assertFalse(self.meta.get("complete"))
        self.assertEqual(self.meta.get("over_limit"), ["big.txt"])

    def test_finalize_pass_is_refused(self):
        fb_path = os.path.join(c.rl_dir(self.repo), "codex-feedback.md")
        pending_before = c.read_json(os.path.join(c.rl_dir(self.repo), "pending.json"), {})

        rc = reviewer.cmd_finalize(self.repo, write_raw(self.repo), "pass", False)

        self.assertNotEqual(rc, 0, "finalize must refuse verdict=pass on an incomplete packet")
        self.assertFalse(os.path.exists(fb_path), "finalize must write nothing when it refuses")
        pending_after = c.read_json(os.path.join(c.rl_dir(self.repo), "pending.json"), {})
        self.assertEqual(pending_after, pending_before, "pending.json must be untouched")
        self.assertEqual(pending_after.get("status"), "pending")

    def test_finalize_needs_changes_allowed_and_stays_active(self):
        rc = reviewer.cmd_finalize(self.repo, write_raw(self.repo), "needs_changes", False)
        self.assertEqual(rc, 0, "a non-pass verdict must still be allowed on an incomplete packet")

        with open(os.path.join(c.rl_dir(self.repo), "codex-feedback.md")) as f:
            header, _ = c.parse_feedback_header(f.read())
        self.assertEqual(header.get("review_incomplete"), "true")

        state = c.read_state(self.repo)
        self.assertFalse(
            state.get("done"),
            "an incomplete review must not close the loop even though "
            "new_findings=False would normally set done=True",
        )


class TestFinalizeMissingCompleteKeyFailsClosed(_RepoCase):
    """D1(b): metadata written before this fix has no 'complete' key at all —
    that must be treated as incomplete-unknown, not as complete."""

    def test_pass_refused_without_complete_key(self):
        n = c.read_state(self.repo).get("iteration", 0) + 1
        meta_path = os.path.join(c.rl_dir(self.repo), "iterations", f"{n:03d}-packet.json")
        c.write_json(meta_path, {
            "cheap_worktree_fp": c.cheap_worktree_fp(self.repo),
            "base_sha": c.base_sha(self.repo),
            "created_at": c.now_iso(),
            # no "complete" key: simulates pre-fix metadata
        })

        rc = reviewer.cmd_finalize(self.repo, write_raw(self.repo), "pass", False)

        self.assertNotEqual(rc, 0, "missing 'complete' key must fail closed, not be treated as complete")
        self.assertFalse(
            os.path.exists(os.path.join(c.rl_dir(self.repo), "codex-feedback.md")))


class TestUnreadableFileMarksIncomplete(_RepoCase):
    """D2: a file that can't even be opened must also flip complete=False."""

    def setUp(self):
        super().setUp()
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            self.skipTest("root can read files regardless of permission bits")
        self.path = os.path.join(self.repo, "secret.bin")
        write_bytes(self.repo, "secret.bin", b"hidden")
        os.chmod(self.path, 0)

    def tearDown(self):
        # Restore permissions before the base tearDown removes the tempdir —
        # addCleanup would run after tempdir removal and fail on the now-gone
        # path.
        try:
            os.chmod(self.path, 0o644)
        except OSError:
            pass
        super().tearDown()

    def test_status_and_packet_report_incomplete(self):
        status = c.untracked_status(self.repo)
        self.assertFalse(status["complete"])
        self.assertIn("secret.bin", status["unreadable"])

        packet = reviewer.build_packet(self.repo, c.worktree_snapshot(self.repo))
        self.assertIn("## REVIEW INCOMPLETE: untracked content over limit", packet)
        self.assertIn("secret.bin", packet)

    def test_fp_parts_record_the_unreadable_marker(self):
        parts = c.untracked_fp_parts(self.repo)
        self.assertTrue(
            any("secret.bin" in p and "unreadable" in p for p in parts),
            f"expected an unreadable marker for secret.bin in {parts!r}",
        )


class TestBoundedReadIgnoresStatLie(_RepoCase):
    """D3: the per-file cap must be enforced against what's actually read,
    not against whatever os.stat happens to report."""

    def setUp(self):
        super().setUp()
        self.env = patch.dict(os.environ, {
            "RL_UNTRACKED_FILE_LIMIT": "100",
            "RL_UNTRACKED_TOTAL_LIMIT": "100000",
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_lying_stat_does_not_bypass_the_cap(self):
        write_bytes(self.repo, "big.bin", b"X" * 10_000)  # 100x the 100-byte limit
        real_stat = os.stat

        def lying_stat(path, *args, **kwargs):
            if str(path).endswith("big.bin"):
                class _TinyStat:
                    st_size = 1  # lies: claims 1 byte
                return _TinyStat()
            return real_stat(path, *args, **kwargs)

        with patch("os.stat", side_effect=lying_stat):
            lied_status = c.untracked_status(self.repo)
            lied_fp = c.cheap_worktree_fp(self.repo)

        real_status = c.untracked_status(self.repo)
        real_fp = c.cheap_worktree_fp(self.repo)

        self.assertFalse(lied_status["complete"])
        self.assertIn("big.bin", lied_status["over_limit"])
        self.assertEqual(
            lied_status, real_status,
            "a lying os.stat() must not change the outcome: the bounded read "
            "decides over-limit status, not a reported/discovered size",
        )
        self.assertEqual(
            lied_fp, real_fp,
            "the over-limit fingerprint must not depend on any (possibly "
            "wrong) size — it never reads past file_limit + 1 bytes",
        )

    def test_10kb_file_under_100_byte_limit_is_over_limit_not_fully_hashed(self):
        write_bytes(self.repo, "small_by_stat_lie.bin", b"Y" * 10_000)
        status = c.untracked_status(self.repo)
        self.assertFalse(status["complete"])
        self.assertIn("small_by_stat_lie.bin", status["over_limit"])
        # A same-sized-but-different-content file must fingerprint identically:
        # if the full 10,000 bytes were being hashed, differing content past
        # byte 100 would change the fp. It must not.
        fp1 = c.cheap_worktree_fp(self.repo)
        write_bytes(self.repo, "small_by_stat_lie.bin", b"Z" * 10_000)
        fp2 = c.cheap_worktree_fp(self.repo)
        self.assertEqual(fp1, fp2)


class TestBoundedReadRespectsTotalBudget(_RepoCase):
    """D3: even a file well within the per-file limit must not be read past
    the remaining total budget."""

    def setUp(self):
        super().setUp()
        self.env = patch.dict(os.environ, {
            "RL_UNTRACKED_FILE_LIMIT": "1000000",
            "RL_UNTRACKED_TOTAL_LIMIT": "250",
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_huge_file_over_remaining_budget_is_unread_not_over_limit(self):
        write_bytes(self.repo, "a.txt", b"a" * 100)
        write_bytes(self.repo, "b.txt", b"b" * 100)
        # Only 50 bytes of total budget remain; this file is nowhere near the
        # (huge) per-file limit, but reading even part of it would blow the
        # total budget, so it must be left unread rather than fully hashed.
        write_bytes(self.repo, "huge.bin", b"c" * 1_000_000)

        status = c.untracked_status(self.repo)
        self.assertFalse(status["complete"])
        self.assertEqual(status["over_limit"], [])
        self.assertEqual(status["unread"], ["huge.bin"])


if __name__ == "__main__":
    unittest.main()
