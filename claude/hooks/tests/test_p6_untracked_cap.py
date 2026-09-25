"""P6: untracked-file content hashing must respect a size cap.

Reading every byte of every untracked file (for the fingerprint and for the
review packet) is slow and makes the packet enormous on a repo with no
.gitignore and huge untracked trees (node_modules, build output, ...).
Per-file and total byte caps (RL_UNTRACKED_FILE_LIMIT / RL_UNTRACKED_TOTAL_LIMIT)
bound how much gets read. When the cap is hit, the check must say so loudly
(INCOMPLETE packet section, untracked_status()["complete"] is False, status
line suffix) instead of silently truncating.
"""
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import review_loop_common as c  # noqa: E402
import reviewer  # noqa: E402
import sessionstart_status  # noqa: E402


def git(repo, *args):
    subprocess.run(
        ["git", "-C", repo, "-c", "user.email=t@t", "-c", "user.name=t", *args],
        check=True, capture_output=True, text=True,
    )


def write_bytes(repo, rel, data):
    with open(os.path.join(repo, rel), "wb") as f:
        f.write(data)


class _RepoCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = self.tmp.name
        git(self.repo, "init", "-q")
        git(self.repo, "commit", "-q", "--allow-empty", "-m", "init")

    def tearDown(self):
        self.tmp.cleanup()


class TestOverFileLimit(_RepoCase):
    """(a) a single file over the per-file limit."""

    def setUp(self):
        super().setUp()
        self.env = patch.dict(os.environ, {
            "RL_UNTRACKED_FILE_LIMIT": "100",
            "RL_UNTRACKED_TOTAL_LIMIT": "250",
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_marked_over_limit_and_status_incomplete(self):
        write_bytes(self.repo, "big.txt", b"A" * 150)
        status = c.untracked_status(self.repo)
        self.assertFalse(status["complete"])
        self.assertEqual(status["over_limit"], ["big.txt"])
        self.assertEqual(status["unread"], [])

    def test_content_not_embedded_and_incomplete_section_present(self):
        marker = b"MARKER_" + b"Z" * 143  # 150 bytes total, unique-ish
        write_bytes(self.repo, "big.txt", marker)
        packet = reviewer.build_packet(self.repo)
        self.assertIn("## REVIEW INCOMPLETE: untracked content over limit", packet)
        self.assertIn("big.txt", packet)
        self.assertNotIn("MARKER_", packet, "over-limit file content must not be embedded")

    def test_editing_content_same_size_does_not_change_fp_but_rename_does(self):
        write_bytes(self.repo, "big.txt", b"A" * 150)
        fp1 = c.cheap_worktree_fp(self.repo)

        write_bytes(self.repo, "big.txt", b"B" * 150)  # same size, different bytes
        fp2 = c.cheap_worktree_fp(self.repo)
        self.assertEqual(fp1, fp2,
                          "an over-limit file is never read, so a same-size content "
                          "edit must not change the fingerprint")

        os.remove(os.path.join(self.repo, "big.txt"))
        write_bytes(self.repo, "renamed.txt", b"B" * 150)
        fp3 = c.cheap_worktree_fp(self.repo)
        self.assertNotEqual(fp2, fp3,
                             "renaming an over-limit file must still change the "
                             "fingerprint (the path is part of the fp)")


class TestTotalLimit(_RepoCase):
    """(b) three files individually under the per-file limit, but the third
    pushes the cumulative read past the total limit."""

    def setUp(self):
        super().setUp()
        self.env = patch.dict(os.environ, {
            "RL_UNTRACKED_FILE_LIMIT": "1000",
            "RL_UNTRACKED_TOTAL_LIMIT": "250",
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_third_file_unread(self):
        write_bytes(self.repo, "a.txt", b"a" * 100)
        write_bytes(self.repo, "b.txt", b"b" * 100)
        write_bytes(self.repo, "c.txt", b"c" * 100)

        status = c.untracked_status(self.repo)
        self.assertFalse(status["complete"])
        self.assertEqual(status["over_limit"], [])
        self.assertEqual(status["unread"], ["c.txt"])

    def test_packet_excludes_unread_file_content(self):
        write_bytes(self.repo, "a.txt", b"a" * 100)
        write_bytes(self.repo, "b.txt", b"b" * 100)
        write_bytes(self.repo, "c.txt", b"c" * 100)

        packet = reviewer.build_packet(self.repo)
        self.assertIn("## REVIEW INCOMPLETE: untracked content over limit", packet)
        self.assertIn("c.txt", packet)
        # a.txt/b.txt were fully read and must still be embedded.
        self.assertIn("aaaaaaaaaa", packet)
        self.assertIn("bbbbbbbbbb", packet)


class TestUnderLimits(_RepoCase):
    """(c) default limits, small files: behavior matches the pre-cap code path."""

    def test_no_incomplete_section_and_fp_changes_on_edit(self):
        with open(os.path.join(self.repo, "small.py"), "w") as f:
            f.write("print('hello')\n")

        status = c.untracked_status(self.repo)
        self.assertTrue(status["complete"])
        self.assertEqual(status["over_limit"], [])
        self.assertEqual(status["unread"], [])

        packet = reviewer.build_packet(self.repo)
        self.assertNotIn("REVIEW INCOMPLETE", packet)
        self.assertIn("print('hello')", packet)

        fp1 = c.cheap_worktree_fp(self.repo)
        with open(os.path.join(self.repo, "small.py"), "w") as f:
            f.write("print('world')\n")
        fp2 = c.cheap_worktree_fp(self.repo)
        self.assertNotEqual(fp1, fp2)


class TestSessionStartStatusSuffix(_RepoCase):
    """(d) sessionstart_status appends the over-limit suffix, still one line."""

    def setUp(self):
        super().setUp()
        os.makedirs(c.rl_dir(self.repo), exist_ok=True)
        open(os.path.join(c.rl_dir(self.repo), "enabled"), "w").close()
        self.env = patch.dict(os.environ, {
            "RL_UNTRACKED_FILE_LIMIT": "100",
            "RL_UNTRACKED_TOTAL_LIMIT": "250",
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_status_line_carries_over_limit_suffix(self):
        write_bytes(self.repo, "big.txt", b"A" * 150)
        line = sessionstart_status.status_line(self.repo)
        self.assertIn("(untracked content over limit: 1 files not fully checked)", line)
        self.assertEqual(len(line.splitlines()), 1, "status line must stay a single line")

    def test_status_line_has_no_suffix_when_under_limits(self):
        with open(os.path.join(self.repo, "small.py"), "w") as f:
            f.write("print('hi')\n")
        line = sessionstart_status.status_line(self.repo)
        self.assertNotIn("untracked content over limit", line)


if __name__ == "__main__":
    unittest.main()
