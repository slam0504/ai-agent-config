"""P8: two Codex round-10 defects on top of the untracked-content cap.

E1: reviewer.cmd_prepare used to derive the packet metadata from one
    untracked-file scan (cheap_worktree_fp_and_status) and the packet body
    from a second, independent scan (build_packet's own untracked_content
    call). A file that changes between the two scans could make the
    metadata say complete=true while the packet it describes actually shows
    REVIEW INCOMPLETE (or vice versa), and `finalize --verdict pass` would
    trust the (wrong) metadata. The fix is exactly ONE scan
    (review_loop_common.worktree_snapshot), shared by both.
E2: _untracked_scan didn't charge an over-limit file's probe read (or the
    read that tips a file into "unread") against the total budget — only
    fully-read/hashed files counted. A tree full of many over-limit files
    could each spend up to file_limit+1 bytes of real disk I/O for free,
    unbounded by the total limit.
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


class TestPrepareUsesExactlyOneScan(_RepoCase):
    """E1: a file growing "between" what used to be two scans must not make
    the metadata and the packet disagree — because there's only one scan."""

    def setUp(self):
        super().setUp()
        self.env = patch.dict(os.environ, {
            "RL_UNTRACKED_FILE_LIMIT": "100",
            "RL_UNTRACKED_TOTAL_LIMIT": "10000",
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_growth_after_the_single_scan_does_not_split_metadata_and_packet(self):
        growing_path = os.path.join(self.repo, "growing.txt")
        write_bytes(self.repo, "growing.txt", b"x" * 10)  # well under the 100-byte limit
        self._stop()  # uses the real (unpatched) scan; not counted below

        real_scan = c._untracked_scan
        calls = {"n": 0}

        def growing_wrapper(root, collect_content=False):
            calls["n"] += 1
            result = real_scan(root, collect_content=collect_content)
            if calls["n"] == 1:
                # Simulate a file changing "between scans": with the old
                # two-scan code, a second scan run after this would see the
                # grown (over-limit) file. With the fix, cmd_prepare never
                # makes a second call, so this must have no effect on its
                # output at all.
                with open(growing_path, "ab") as f:
                    f.write(b"y" * 200)
            return result

        with patch.object(c, "_untracked_scan", side_effect=growing_wrapper):
            rc = reviewer.cmd_prepare(self.repo)

        self.assertEqual(rc, 0)
        self.assertEqual(calls["n"], 1, "cmd_prepare must perform exactly one untracked scan")

        meta = c.read_json(
            os.path.join(c.rl_dir(self.repo), "iterations", "001-packet.json"), {})
        with open(os.path.join(c.rl_dir(self.repo), "iterations", "001-packet.md")) as f:
            packet = f.read()
        has_banner = "REVIEW INCOMPLETE" in packet

        # A single scan sees the pre-growth (10-byte, under-limit) file, so
        # both metadata and packet must agree it was complete.
        self.assertTrue(meta.get("complete"))
        self.assertFalse(has_banner)
        self.assertEqual(meta.get("complete"), not has_banner)


class TestMetadataCompleteAgreesWithPacketBanner(_RepoCase):
    """E1 (direct): metadata.complete must always equal the absence of the
    REVIEW INCOMPLETE banner in the packet built alongside it."""

    def _prepare_and_check(self):
        rc = reviewer.cmd_prepare(self.repo)
        self.assertEqual(rc, 0)
        meta = c.read_json(
            os.path.join(c.rl_dir(self.repo), "iterations", "001-packet.json"), {})
        with open(os.path.join(c.rl_dir(self.repo), "iterations", "001-packet.md")) as f:
            packet = f.read()
        has_banner = "REVIEW INCOMPLETE" in packet
        self.assertEqual(meta.get("complete"), not has_banner)
        return meta, has_banner

    def test_complete_tree_has_no_banner(self):
        write_bytes(self.repo, "small.txt", b"hi")
        self._stop()
        meta, has_banner = self._prepare_and_check()
        self.assertTrue(meta.get("complete"))
        self.assertFalse(has_banner)

    def test_incomplete_tree_has_banner(self):
        self.env = patch.dict(os.environ, {
            "RL_UNTRACKED_FILE_LIMIT": "10",
            "RL_UNTRACKED_TOTAL_LIMIT": "1000",
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        write_bytes(self.repo, "big.txt", b"X" * 50)
        self._stop()
        meta, has_banner = self._prepare_and_check()
        self.assertFalse(meta.get("complete"))
        self.assertTrue(has_banner)


class TestTotalBudgetChargesEveryReadByte(_RepoCase):
    """E2: over-limit probe reads (and the read that tips a file into
    "unread") must count against the total budget, and the scan must stop
    opening files once the budget is gone."""

    def setUp(self):
        super().setUp()
        self.env = patch.dict(os.environ, {
            "RL_UNTRACKED_FILE_LIMIT": "100",
            "RL_UNTRACKED_TOTAL_LIMIT": "250",
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_ten_over_limit_files_bounded_total_read_and_open_count(self):
        names = [f"f{i:02d}.bin" for i in range(10)]
        for name in names:
            write_bytes(self.repo, name, b"X" * 150)

        real_open = open
        opened_paths = []
        bytes_read = []

        def counting_open(path, mode="r", *args, **kwargs):
            fh = real_open(path, mode, *args, **kwargs)
            if mode == "rb" and str(path).startswith(self.repo):
                opened_paths.append(path)
                orig_read = fh.read

                def counted_read(*a, **kw):
                    data = orig_read(*a, **kw)
                    bytes_read.append(len(data))
                    return data
                fh.read = counted_read
            return fh

        with patch("builtins.open", side_effect=counting_open):
            status = c.untracked_status(self.repo)

        total_limit = c.current_untracked_limits()[1]
        total_actually_read = sum(bytes_read)

        self.assertFalse(status["complete"])
        self.assertLessEqual(
            len(opened_paths), 3,
            f"expected at most 3 files to ever be opened, got {len(opened_paths)}",
        )
        self.assertLessEqual(
            total_actually_read, total_limit + len(opened_paths),
            "total bytes read must be bounded by the total limit plus one "
            "probe byte per file actually opened — over-limit probe reads "
            "must count against the budget",
        )
        self.assertEqual(
            len(status["over_limit"]) + len(status["unread"]), 10,
            "every file must be accounted for as either over_limit or unread",
        )
        # The files that were never opened at all must be exactly the ones
        # left unread once the budget ran out.
        self.assertGreaterEqual(len(status["unread"]), 10 - len(opened_paths))


if __name__ == "__main__":
    unittest.main()
