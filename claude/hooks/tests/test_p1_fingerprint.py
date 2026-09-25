"""P1: cheap_worktree_fp() must be content-aware.

R1: finalize must stamp the fingerprint captured when the packet was built
(prepare time), read exclusively from per-packet metadata — never from
pending.json, which a later Stop can overwrite for a newer, different tree
before this review is finalized — and must refuse to finalize when that
metadata is missing.
"""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import consume_feedback  # noqa: E402
import review_loop_common as c  # noqa: E402
import reviewer  # noqa: E402
import stop_enqueue  # noqa: E402


def git(repo, *args):
    subprocess.run(
        ["git", "-C", repo, "-c", "user.email=t@t", "-c", "user.name=t", *args],
        check=True, capture_output=True, text=True,
    )


def enable_review_loop(repo):
    d = c.rl_dir(repo)
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "enabled"), "w").close()


class TestFingerprintContentAware(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = self.tmp.name
        git(self.repo, "init", "-q")
        with open(os.path.join(self.repo, "a.py"), "w") as f:
            f.write("value = 0\n")
        git(self.repo, "add", "a.py")
        git(self.repo, "commit", "-q", "-m", "init")

    def tearDown(self):
        self.tmp.cleanup()

    def test_same_line_content_change_changes_fingerprint(self):
        with open(os.path.join(self.repo, "a.py"), "w") as f:
            f.write("value = 1\n")
        fp1 = c.cheap_worktree_fp(self.repo)

        with open(os.path.join(self.repo, "a.py"), "w") as f:
            f.write("value = 9\n")
        fp9 = c.cheap_worktree_fp(self.repo)

        self.assertNotEqual(
            fp1, fp9,
            "changing a value on the same line must change the worktree fingerprint",
        )


class TestFinalizeUsesPacketTimeFingerprint(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = self.tmp.name
        git(self.repo, "init", "-q")
        with open(os.path.join(self.repo, "a.py"), "w") as f:
            f.write("value = 0\n")
        git(self.repo, "add", "a.py")
        git(self.repo, "commit", "-q", "-m", "init")
        enable_review_loop(self.repo)

    def tearDown(self):
        self.tmp.cleanup()

    def _write_raw_feedback(self, text="some findings"):
        raw_path = os.path.join(self.repo, "raw-feedback.txt")
        with open(raw_path, "w") as f:
            f.write(text)
        return raw_path

    def test_finalize_ignores_pending_json_rewritten_after_prepare(self):
        # Tree A: what gets prepared and (eventually) reviewed.
        with open(os.path.join(self.repo, "a.py"), "w") as f:
            f.write("value = 1\n")
        c.write_json(os.path.join(c.rl_dir(self.repo), "pending.json"), {
            "status": "pending",
            "cheap_worktree_fp": c.cheap_worktree_fp(self.repo),
        })
        rc = reviewer.cmd_prepare(self.repo)
        self.assertEqual(rc, 0)
        prepare_time_fp = c.read_json(
            os.path.join(c.rl_dir(self.repo), "iterations", "001-packet.json"), {}
        )["cheap_worktree_fp"]

        # Tree B: edited *during* the review; a second Stop fires and rewrites
        # pending.json for the new tree, via the real stop_enqueue.py path.
        with open(os.path.join(self.repo, "a.py"), "w") as f:
            f.write("value = 42\n")
        stop_enqueue.run(json.dumps({"cwd": self.repo}))
        rewritten_pending = c.read_json(os.path.join(c.rl_dir(self.repo), "pending.json"), {})
        current_fp = c.cheap_worktree_fp(self.repo)
        self.assertEqual(rewritten_pending.get("cheap_worktree_fp"), current_fp)
        self.assertNotEqual(prepare_time_fp, current_fp, "test setup should actually change the tree")

        rc = reviewer.cmd_finalize(self.repo, self._write_raw_feedback(), "needs_changes", True)
        self.assertEqual(rc, 0)

        with open(os.path.join(c.rl_dir(self.repo), "codex-feedback.md")) as f:
            feedback_md = f.read()
        header, _ = c.parse_feedback_header(feedback_md)

        self.assertEqual(
            header.get("reviewed_worktree_fp"), prepare_time_fp,
            "finalize must stamp the packet's own fingerprint, not whatever "
            "pending.json currently holds",
        )

        # A subsequent consume check, against the now-current tree B, must
        # flag this feedback as stale rather than inject it as fresh.
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            consume_feedback.run(json.dumps({"cwd": self.repo}))
        self.assertIn("STALE", stdout.getvalue())

    def test_finalize_leaves_newer_pending_tree_unreviewed(self):
        # Prepare tree A, then a second Stop rewrites pending.json for tree B.
        with open(os.path.join(self.repo, "a.py"), "w") as f:
            f.write("value = 1\n")
        c.write_json(os.path.join(c.rl_dir(self.repo), "pending.json"), {
            "status": "pending",
            "cheap_worktree_fp": c.cheap_worktree_fp(self.repo),
        })
        self.assertEqual(reviewer.cmd_prepare(self.repo), 0)
        with open(os.path.join(self.repo, "a.py"), "w") as f:
            f.write("value = 42\n")
        stop_enqueue.run(json.dumps({"cwd": self.repo}))
        fp_b = c.cheap_worktree_fp(self.repo)

        # (raw feedback is written before finalize; it is itself an untracked
        # file, so compare against fp_b captured above, not a fresh fp.)
        self.assertEqual(
            reviewer.cmd_finalize(self.repo, self._write_raw_feedback(), "needs_changes", True), 0)

        # Tree B was never reviewed: finalizing A must not consume B's marker,
        # otherwise `prepare` for B reports "no pending review" until the tree
        # changes yet again.
        pending = c.read_json(os.path.join(c.rl_dir(self.repo), "pending.json"), {})
        self.assertEqual(pending.get("status"), "pending")
        self.assertEqual(pending.get("cheap_worktree_fp"), fp_b)

    def test_second_prepare_in_same_round_is_refused_and_keeps_first_packet(self):
        # prepare A → edit to B → Stop → prepare B again in the same round.
        # `iteration` only advances in finalize, so the second prepare would
        # target the same 001-packet.* files and overwrite A's metadata.
        with open(os.path.join(self.repo, "a.py"), "w") as f:
            f.write("value = 1\n")
        stop_enqueue.run(json.dumps({"cwd": self.repo}))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(reviewer.cmd_prepare(self.repo), 0)
        meta_path = os.path.join(c.rl_dir(self.repo), "iterations", "001-packet.json")
        packet_path = os.path.join(c.rl_dir(self.repo), "iterations", "001-packet.md")
        fp_a = c.read_json(meta_path, {})["cheap_worktree_fp"]
        with open(packet_path) as f:
            packet_a = f.read()

        with open(os.path.join(self.repo, "a.py"), "w") as f:
            f.write("value = 42\n")
        stop_enqueue.run(json.dumps({"cwd": self.repo}))
        fp_b = c.cheap_worktree_fp(self.repo)
        self.assertNotEqual(fp_a, fp_b)

        stderr = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(stderr):
            rc = reviewer.cmd_prepare(self.repo)
        self.assertNotEqual(rc, 0, "second prepare in the same round must be refused")
        self.assertTrue(stderr.getvalue().strip())
        self.assertEqual(c.read_json(meta_path, {})["cheap_worktree_fp"], fp_a,
                         "A's metadata must survive the refused prepare")
        with open(packet_path) as f:
            self.assertEqual(f.read(), packet_a, "A's packet must survive the refused prepare")

        # Finalizing A must still stamp A's fp and leave B pending.
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(
                reviewer.cmd_finalize(self.repo, self._write_raw_feedback(), "needs_changes", True), 0)
        with open(os.path.join(c.rl_dir(self.repo), "codex-feedback.md")) as f:
            header, _ = c.parse_feedback_header(f.read())
        self.assertEqual(header.get("reviewed_worktree_fp"), fp_a)
        pending = c.read_json(os.path.join(c.rl_dir(self.repo), "pending.json"), {})
        self.assertEqual(pending.get("status"), "pending")
        self.assertEqual(pending.get("cheap_worktree_fp"), fp_b)

    def test_finalize_refuses_when_packet_metadata_missing(self):
        with open(os.path.join(self.repo, "a.py"), "w") as f:
            f.write("value = 1\n")
        c.write_json(os.path.join(c.rl_dir(self.repo), "pending.json"), {
            "status": "pending",
            "cheap_worktree_fp": c.cheap_worktree_fp(self.repo),
        })
        # No cmd_prepare call: no NNN-packet.json metadata exists.

        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            rc = reviewer.cmd_finalize(self.repo, self._write_raw_feedback(), "needs_changes", True)

        self.assertNotEqual(rc, 0, "finalize must fail loudly without packet metadata")
        self.assertTrue(stderr.getvalue().strip(), "finalize must explain the failure on stderr")
        self.assertFalse(
            os.path.exists(os.path.join(c.rl_dir(self.repo), "codex-feedback.md")),
            "finalize must not fabricate feedback when it has no trustworthy fingerprint",
        )


if __name__ == "__main__":
    unittest.main()
