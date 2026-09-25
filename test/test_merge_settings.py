"""Tests for claude/merge-settings.py.

Invokes the script as a subprocess (its filename has a hyphen, so it isn't a
plain importable module) against temp repo/dest/backup paths — this mirrors
exactly how install.sh calls it.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO_DIR, "claude", "merge-settings.py")


def run_merge(repo_settings, dest_path, backup_dir, home=None):
    repo_path = os.path.join(os.path.dirname(dest_path), "_repo-settings.json")
    with open(repo_path, "w", encoding="utf-8") as f:
        json.dump(repo_settings, f)
    env = dict(os.environ)
    if home is not None:
        env["HOME"] = home
    proc = subprocess.run(
        [sys.executable, SCRIPT, repo_path, dest_path, backup_dir],
        capture_output=True,
        text=True,
        env=env,
    )
    return proc


def substitute_home_in_json(obj, home):
    """Deep-copy obj with every literal "$HOME" substring replaced by home,
    via a JSON round-trip (used to build a local settings fixture that mirrors
    the repo's hook commands but in absolute-path form)."""
    return json.loads(json.dumps(obj).replace("$HOME", home))


class MergeSettingsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dest = os.path.join(self.tmp.name, "settings.json")
        self.backup_dir = os.path.join(self.tmp.name, "backup")

        self.repo_settings = {
            "permissions": {"defaultMode": "auto"},
            "hooks": {
                "SessionStart": [
                    {
                        "hooks": [
                            {
                                "type": "command",
                                "command": "bash \"$HOME/.claude/hooks/sessionstart-restore.sh\"",
                            }
                        ]
                    }
                ],
                "Stop": [
                    {
                        "hooks": [
                            {
                                "type": "command",
                                "command": "bash \"$HOME/.claude/hooks/review-loop-stop.sh\"",
                            }
                        ]
                    }
                ],
            },
            "enabledPlugins": {"serena@x": True, "codex@y": True},
            "language": "繁體中文",
            "effortLevel": "high",
        }

    def write_dest(self, content):
        with open(self.dest, "w", encoding="utf-8") as f:
            json.dump(content, f)

    def read_dest(self):
        with open(self.dest, "r", encoding="utf-8") as f:
            return json.load(f)

    # -- managed scalar override --------------------------------------

    def test_managed_scalar_override(self):
        self.write_dest({"language": "English", "effortLevel": "low"})
        proc = run_merge(self.repo_settings, self.dest, self.backup_dir)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        merged = self.read_dest()
        self.assertEqual(merged["language"], "繁體中文")
        self.assertEqual(merged["effortLevel"], "high")

    # -- enabledPlugins union -------------------------------------------

    def test_enabled_plugins_union_preserves_local_only(self):
        self.write_dest({"enabledPlugins": {"local-only@z": True, "serena@x": False}})
        proc = run_merge(self.repo_settings, self.dest, self.backup_dir)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        merged = self.read_dest()
        self.assertEqual(
            merged["enabledPlugins"],
            {"local-only@z": True, "serena@x": True, "codex@y": True},
        )

    # -- permissions ------------------------------------------------------

    def test_permissions_allow_and_additional_directories_preserved(self):
        self.write_dest(
            {
                "permissions": {
                    "defaultMode": "manual",
                    "allow": ["Bash(go test:*)", "Bash(git status:*)"],
                    "additionalDirectories": ["/Users/x/.claude"],
                }
            }
        )
        proc = run_merge(self.repo_settings, self.dest, self.backup_dir)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        merged = self.read_dest()
        self.assertEqual(merged["permissions"]["defaultMode"], "auto")
        self.assertEqual(
            merged["permissions"]["allow"],
            ["Bash(go test:*)", "Bash(git status:*)"],
        )
        self.assertEqual(
            merged["permissions"]["additionalDirectories"], ["/Users/x/.claude"]
        )

    # -- hooks --------------------------------------------------------------

    def test_hooks_existing_group_same_matcher_gets_missing_command_appended(self):
        self.write_dest(
            {
                "hooks": {
                    "SessionStart": [{"hooks": [{"type": "command", "command": "existing-cmd"}]}]
                }
            }
        )
        proc = run_merge(self.repo_settings, self.dest, self.backup_dir)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        merged = self.read_dest()
        commands = [h["command"] for h in merged["hooks"]["SessionStart"][0]["hooks"]]
        self.assertIn("existing-cmd", commands)
        self.assertIn(
            'bash "$HOME/.claude/hooks/sessionstart-restore.sh"', commands
        )
        self.assertEqual(len(merged["hooks"]["SessionStart"]), 1)

    def test_hooks_duplicate_command_not_re_added(self):
        self.write_dest(
            {
                "hooks": {
                    "SessionStart": [
                        {
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": 'bash "$HOME/.claude/hooks/sessionstart-restore.sh"',
                                }
                            ]
                        }
                    ]
                }
            }
        )
        proc = run_merge(self.repo_settings, self.dest, self.backup_dir)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        merged = self.read_dest()
        self.assertEqual(len(merged["hooks"]["SessionStart"][0]["hooks"]), 1)

    def test_hooks_local_only_stop_hook_preserved(self):
        self.write_dest(
            {
                "hooks": {
                    "Stop": [
                        {
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "/usr/local/bin/python3 /Users/x/playground/telegram/stop_hook.py",
                                }
                            ]
                        }
                    ]
                }
            }
        )
        proc = run_merge(self.repo_settings, self.dest, self.backup_dir)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        merged = self.read_dest()
        commands = [h["command"] for h in merged["hooks"]["Stop"][0]["hooks"]]
        self.assertIn(
            "/usr/local/bin/python3 /Users/x/playground/telegram/stop_hook.py", commands
        )
        self.assertIn('bash "$HOME/.claude/hooks/review-loop-stop.sh"', commands)

    def test_hooks_repo_only_event_appended(self):
        self.write_dest({"hooks": {"SessionEnd": [{"matcher": "", "hooks": [{"type": "command", "command": "cleanup"}]}]}})
        proc = run_merge(self.repo_settings, self.dest, self.backup_dir)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        merged = self.read_dest()
        self.assertIn("SessionStart", merged["hooks"])
        self.assertIn("Stop", merged["hooks"])
        # local-only event/group untouched
        self.assertEqual(
            merged["hooks"]["SessionEnd"],
            [{"matcher": "", "hooks": [{"type": "command", "command": "cleanup"}]}],
        )

    def test_hooks_matcher_empty_string_and_missing_are_distinct(self):
        self.write_dest(
            {
                "hooks": {
                    "PreToolUse": [
                        {"matcher": "", "hooks": [{"type": "command", "command": "local-empty-matcher"}]}
                    ]
                }
            }
        )
        repo_settings = {
            "hooks": {
                "PreToolUse": [{"hooks": [{"type": "command", "command": "repo-no-matcher"}]}]
            }
        }
        proc = run_merge(repo_settings, self.dest, self.backup_dir)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        merged = self.read_dest()
        groups = merged["hooks"]["PreToolUse"]
        self.assertEqual(len(groups), 2)
        self.assertEqual(sum(1 for g in groups if "matcher" in g), 1)
        self.assertEqual(sum(1 for g in groups if "matcher" not in g), 1)

    def test_hooks_path_form_equivalent_command_not_duplicated(self):
        """Regression: a local command using an absolute $HOME expansion must
        be recognised as the same command as the repo's $HOME-form version."""
        home = "/Users/testhome"
        self.write_dest(
            {
                "hooks": {
                    "SessionStart": [
                        {"hooks": [{"type": "command", "command": f'bash "{home}/.claude/hooks/x.sh"'}]}
                    ]
                }
            }
        )
        repo_settings = {
            "hooks": {
                "SessionStart": [
                    {"hooks": [{"type": "command", "command": 'bash "$HOME/.claude/hooks/x.sh"'}]}
                ]
            }
        }
        proc = run_merge(repo_settings, self.dest, self.backup_dir, home=home)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("settings unchanged", proc.stdout)
        merged = self.read_dest()
        commands = [h["command"] for h in merged["hooks"]["SessionStart"][0]["hooks"]]
        self.assertEqual(commands, [f'bash "{home}/.claude/hooks/x.sh"'])

    def test_hooks_command_in_second_matcher_less_group_not_duplicated_in_first(self):
        """Regression: dedupe must look across ALL same-matcher local groups,
        not just the first one found."""
        self.write_dest(
            {
                "hooks": {
                    "Stop": [
                        {"hooks": [{"type": "command", "command": "telegram-hook"}]},
                        {"hooks": [{"type": "command", "command": "repo-stop-cmd"}]},
                    ]
                }
            }
        )
        repo_settings = {
            "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "repo-stop-cmd"}]}]}
        }
        proc = run_merge(repo_settings, self.dest, self.backup_dir)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("settings unchanged", proc.stdout)
        merged = self.read_dest()
        self.assertEqual(len(merged["hooks"]["Stop"]), 2)
        first_group_commands = [h["command"] for h in merged["hooks"]["Stop"][0]["hooks"]]
        self.assertEqual(first_group_commands, ["telegram-hook"])

    def test_hooks_genuinely_new_command_appended_once_then_idempotent(self):
        self.write_dest(
            {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "telegram-hook"}]}]}}
        )
        repo_settings = {
            "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "new-repo-cmd"}]}]}
        }
        proc1 = run_merge(repo_settings, self.dest, self.backup_dir)
        self.assertEqual(proc1.returncode, 0, proc1.stderr)
        merged = self.read_dest()
        commands = [h["command"] for h in merged["hooks"]["Stop"][0]["hooks"]]
        self.assertEqual(commands, ["telegram-hook", "new-repo-cmd"])

        proc2 = run_merge(repo_settings, self.dest, self.backup_dir)
        self.assertEqual(proc2.returncode, 0, proc2.stderr)
        self.assertIn("settings unchanged", proc2.stdout)

    def test_real_shape_multi_group_hooks_report_unchanged(self):
        """Mirrors the real ~/.claude/settings.json shape that exposed the bug:
        SessionStart with three matcher-less groups plus one matcher: ""
        group, and Stop with a local-only Telegram group alongside a group
        that already has the repo's command under an absolute path."""
        repo_path = os.path.join(REPO_DIR, "claude", "settings.json")
        with open(repo_path, encoding="utf-8") as f:
            repo_settings = json.load(f)

        home = "/Users/testhome"
        local = substitute_home_in_json(repo_settings, home)
        local["hooks"]["Stop"].insert(
            0,
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": f"/usr/local/bin/python3 {home}/playground/telegram/stop_hook.py",
                    }
                ]
            },
        )
        local["permissions"]["allow"] = ["Bash(go test:*)"]
        local["permissions"]["additionalDirectories"] = [f"{home}/.claude"]

        self.write_dest(local)
        counts_before = {
            event: sum(len(g.get("hooks", [])) for g in local["hooks"][event])
            for event in ("SessionStart", "Stop", "PreCompact")
        }

        proc = run_merge(repo_settings, self.dest, self.backup_dir, home=home)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("settings unchanged", proc.stdout)

        merged = self.read_dest()
        counts_after = {
            event: sum(len(g.get("hooks", [])) for g in merged["hooks"][event])
            for event in ("SessionStart", "Stop", "PreCompact")
        }
        self.assertEqual(counts_after, counts_before)

    # -- env / local-only top-level key preserved ----------------------------

    def test_env_preserved(self):
        self.write_dest({"env": {"PATH": "/usr/local/bin:/usr/bin"}})
        proc = run_merge(self.repo_settings, self.dest, self.backup_dir)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        merged = self.read_dest()
        self.assertEqual(merged["env"], {"PATH": "/usr/local/bin:/usr/bin"})

    # -- idempotency ----------------------------------------------------------

    def test_idempotent_second_run_reports_unchanged_and_bytes_identical(self):
        self.write_dest({"language": "English"})
        proc1 = run_merge(self.repo_settings, self.dest, self.backup_dir)
        self.assertEqual(proc1.returncode, 0, proc1.stderr)
        with open(self.dest, "rb") as f:
            bytes_after_first = f.read()

        proc2 = run_merge(self.repo_settings, self.dest, self.backup_dir)
        self.assertEqual(proc2.returncode, 0, proc2.stderr)
        self.assertIn("unchanged", proc2.stdout)
        with open(self.dest, "rb") as f:
            bytes_after_second = f.read()
        self.assertEqual(bytes_after_first, bytes_after_second)

    # -- invalid JSON ----------------------------------------------------------

    def test_invalid_dest_json_exits_2_and_dest_untouched(self):
        with open(self.dest, "w", encoding="utf-8") as f:
            f.write("{ not valid json")
        with open(self.dest, "r", encoding="utf-8") as f:
            before = f.read()
        proc = run_merge(self.repo_settings, self.dest, self.backup_dir)
        self.assertEqual(proc.returncode, 2)
        with open(self.dest, "r", encoding="utf-8") as f:
            after = f.read()
        self.assertEqual(before, after)

    # -- missing dest -----------------------------------------------------------

    def test_missing_dest_created_with_repo_content(self):
        self.assertFalse(os.path.exists(self.dest))
        proc = run_merge(self.repo_settings, self.dest, self.backup_dir)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        merged = self.read_dest()
        self.assertEqual(merged["language"], "繁體中文")
        self.assertEqual(merged["permissions"]["defaultMode"], "auto")
        self.assertIn("SessionStart", merged["hooks"])


if __name__ == "__main__":
    unittest.main()
