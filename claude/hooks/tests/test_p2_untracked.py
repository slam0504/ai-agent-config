"""P2: an untracked (non-ignored) file must count as dirty, and its content must
show up in the review packet built from it.

R2: the untracked-file fingerprint must (a) actually find non-ASCII-named
files instead of choking on git's quoted-path output, and (b) hash raw bytes
so distinct invalid-UTF-8 content doesn't collide under lossy text decoding.
"""
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import review_loop_common as c  # noqa: E402
import reviewer  # noqa: E402


def git(repo, *args):
    subprocess.run(
        ["git", "-C", repo, "-c", "user.email=t@t", "-c", "user.name=t", *args],
        check=True, capture_output=True, text=True,
    )


class TestUntrackedFileTriggersReview(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = self.tmp.name
        git(self.repo, "init", "-q")
        git(self.repo, "commit", "-q", "--allow-empty", "-m", "init")

    def tearDown(self):
        self.tmp.cleanup()

    def test_tree_dirty_true_for_untracked_only(self):
        with open(os.path.join(self.repo, "new_file.py"), "w") as f:
            f.write("print('hello from untracked file')\n")

        self.assertTrue(
            c.tree_dirty(self.repo),
            "a repo whose only change is a new untracked file must be reported dirty",
        )

    def test_review_packet_includes_untracked_file_content(self):
        marker = "UNIQUE_UNTRACKED_MARKER_12345"
        with open(os.path.join(self.repo, "new_file.py"), "w") as f:
            f.write(f"# {marker}\n")

        packet = reviewer.build_packet(self.repo)

        self.assertIn(marker, packet, "the review packet must include untracked file content")


class TestUntrackedFingerprintByteAware(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = self.tmp.name
        git(self.repo, "init", "-q")
        git(self.repo, "commit", "-q", "--allow-empty", "-m", "init")

    def tearDown(self):
        self.tmp.cleanup()

    def test_editing_non_ascii_named_untracked_file_changes_fingerprint(self):
        fname = "測試.py"
        path = os.path.join(self.repo, fname)
        with open(path, "w", encoding="utf-8") as f:
            f.write("first\n")
        fp1 = c.cheap_worktree_fp(self.repo)

        with open(path, "w", encoding="utf-8") as f:
            f.write("second\n")
        fp2 = c.cheap_worktree_fp(self.repo)

        self.assertNotEqual(
            fp1, fp2,
            "editing a non-ASCII-named untracked file must change the fingerprint "
            "(git quotes the path by default; it must not be silently dropped)",
        )

        packet = reviewer.build_packet(self.repo)
        self.assertIn(fname, packet, "the packet must list the non-ASCII filename")
        self.assertIn("second", packet, "the packet must include the file's actual content")

    def test_different_invalid_utf8_content_does_not_collide(self):
        path = os.path.join(self.repo, "binary.dat")
        with open(path, "wb") as f:
            f.write(b"\xff\xfe")
        fp1 = c.cheap_worktree_fp(self.repo)

        with open(path, "wb") as f:
            f.write(b"\xfe\xff")
        fp2 = c.cheap_worktree_fp(self.repo)

        self.assertNotEqual(
            fp1, fp2,
            "different invalid-UTF-8 byte contents must not hash to the same fingerprint",
        )


if __name__ == "__main__":
    unittest.main()
