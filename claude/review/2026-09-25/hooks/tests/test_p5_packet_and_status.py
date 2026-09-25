"""Regression tests for the fourth Codex review round.

P5a: the review packet must include staged changes even when the worktree
     copy was reverted (fingerprint counts them, so the packet must show them).
P5b: a new pending marker written after a finished round must be reported by
     the SessionStart status line instead of the previous round's idle state.
"""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest

HOOKS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HOOKS)
import review_loop_common as c  # noqa: E402
import reviewer  # noqa: E402
import sessionstart_status  # noqa: E402
import stop_enqueue  # noqa: E402


def git(repo, *args):
    subprocess.run(["git", "-C", repo, "-c", "user.email=t@t", "-c", "user.name=t", *args],
                   check=True, capture_output=True)


class _RepoCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = self.tmp.name
        git(self.repo, "init", "-q")
        self._write("a.py", "value = 0\n")
        git(self.repo, "add", "a.py")
        git(self.repo, "commit", "-q", "-m", "init")
        os.makedirs(c.rl_dir(self.repo), exist_ok=True)
        open(os.path.join(c.rl_dir(self.repo), "enabled"), "w").close()

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, rel, text):
        with open(os.path.join(self.repo, rel), "w") as f:
            f.write(text)

    def _stop(self):
        stop_enqueue.run(json.dumps({"cwd": self.repo}))

    def _prepare(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(reviewer.cmd_prepare(self.repo), 0)


class TestPacketIncludesStagedChanges(_RepoCase):
    def test_staged_but_reverted_in_worktree_appears_in_packet(self):
        self._write("a.py", "value = 999\n")
        git(self.repo, "add", "a.py")
        self._write("a.py", "value = 0\n")  # worktree back to HEAD; index still 999
        self.assertTrue(c.tree_dirty(self.repo))
        self._stop()
        self._prepare()
        with open(os.path.join(c.rl_dir(self.repo), "iterations", "001-packet.md")) as f:
            packet = f.read()
        self.assertIn("999", packet, "staged content must be visible to the reviewer")
        self.assertIn("staged", packet)
        self.assertIn("unstaged", packet)


class TestStatusReportsNewPendingAfterDone(_RepoCase):
    def test_new_pending_outranks_previous_round_done(self):
        self._write("a.py", "value = 1\n")
        self._stop()
        self._prepare()
        raw = os.path.join(self.repo, "raw.txt")
        with open(raw, "w") as f:
            f.write("looks good")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(reviewer.cmd_finalize(self.repo, raw, "pass", False), 0)
        self.assertTrue(c.read_state(self.repo).get("done"))

        self._write("a.py", "value = 2\n")
        self._stop()
        pending = c.read_json(os.path.join(c.rl_dir(self.repo), "pending.json"), {})
        self.assertEqual(pending.get("status"), "pending")

        line = sessionstart_status.status_line(self.repo)
        self.assertEqual(line, "review-loop: pending review")

    def test_done_without_new_pending_still_idle(self):
        self._write("a.py", "value = 1\n")
        self._stop()
        self._prepare()
        raw = os.path.join(self.repo, "raw.txt")
        with open(raw, "w") as f:
            f.write("looks good")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(reviewer.cmd_finalize(self.repo, raw, "pass", False), 0)
        # pending.json now has status "reviewed" (fp unchanged since prepare... except raw.txt)
        pending = c.read_json(os.path.join(c.rl_dir(self.repo), "pending.json"), {})
        pending["status"] = "reviewed"
        c.write_json(os.path.join(c.rl_dir(self.repo), "pending.json"), pending)
        self.assertTrue(sessionstart_status.status_line(self.repo).startswith("review-loop: idle"))


if __name__ == "__main__":
    unittest.main()
