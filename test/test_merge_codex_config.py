import contextlib
import datetime
import importlib.util
import io
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "codex" / "merge-config.py"
SPEC = importlib.util.spec_from_file_location("merge_codex_config", SCRIPT)
MERGER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MERGER)


class MergeCodexConfigTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.template = self.root / "template.toml"
        self.overlay = self.root / "local.toml"
        self.destination = self.root / "home" / ".codex" / "config.toml"
        self.backup_dir = self.root / "backups"
        self.template.write_text('model = "new-model"\n[features]\nmemories = true\n')

    def seed_local(self, text):
        self.destination.parent.mkdir(parents=True, exist_ok=True)
        self.destination.write_text(text)
        self.destination.chmod(0o600)

    def install(self, force=False):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return MERGER.install(self.template, self.overlay, self.destination, self.backup_dir, force)

    def read_result(self):
        return tomllib.loads(self.destination.read_text())

    def test_first_install_without_overlay_uses_private_permissions(self):
        self.assertEqual(self.install(), 0)
        self.assertEqual(self.read_result(), {"model": "new-model", "features": {"memories": True}})
        self.assertEqual(stat.S_IMODE(self.destination.stat().st_mode), 0o600)

    def test_overlay_adds_machine_specific_settings(self):
        self.overlay.write_text('[projects."/local/project"]\ntrust_level = "trusted"\n')
        self.assertEqual(self.install(), 0)
        self.assertEqual(self.read_result()["projects"]["/local/project"]["trust_level"], "trusted")

    def test_local_only_app_settings_do_not_trigger_drift(self):
        self.seed_local('''model = "new-model"
notify = ["/local/notify", "turn-ended"]
[features]
memories = true
fast_mode = true
[plugins."browser@bundled"]
enabled = true
[mcp_servers.node_repl]
command = "/local/node_repl"
[mcp_servers.node_repl.env]
PRIVATE_VALUE = "local-only"
[desktop]
followUpQueueMode = "steer"
''')
        original = self.destination.read_bytes()
        self.assertEqual(self.install(), 0)
        self.assertEqual(self.destination.read_bytes(), original)
        self.assertFalse(self.backup_dir.exists())

    def test_force_changes_managed_values_and_preserves_local_siblings(self):
        self.seed_local('''model = "old-model"
notify = ["/local/notify"]
[features]
memories = false
fast_mode = true
[mcp_servers.playwright]
command = "npx"
startup_timeout_sec = 90
[mcp_servers.node_repl]
command = "/local/node_repl"
[plugins."local@bundled"]
enabled = true
[marketplaces.bundled]
source = "/local/bundled"
source_type = "local"
''')
        self.template.write_text(self.template.read_text() + '[mcp_servers.playwright]\ncommand = "new-command"\n')
        original = self.read_result()
        self.assertEqual(self.install(force=True), 0)
        result = self.read_result()
        self.assertEqual(result["model"], "new-model")
        self.assertTrue(result["features"]["memories"])
        self.assertTrue(result["features"]["fast_mode"])
        self.assertEqual(result["mcp_servers"]["playwright"], {"command": "new-command", "startup_timeout_sec": 90})
        for key in ("notify", "plugins", "marketplaces"):
            self.assertEqual(result[key], original[key])
        self.assertEqual(result["mcp_servers"]["node_repl"], original["mcp_servers"]["node_repl"])

    def test_managed_conflict_skips_without_force(self):
        self.seed_local('model = "local-choice"\n')
        original = self.destination.read_bytes()
        self.assertEqual(self.install(), 3)
        self.assertEqual(self.destination.read_bytes(), original)
        self.assertFalse(self.backup_dir.exists())

    def test_new_managed_keys_are_added_without_force(self):
        self.seed_local('model = "new-model"\n[desktop]\nmode = "local"\n')
        self.assertEqual(self.install(), 0)
        self.assertTrue(self.read_result()["features"]["memories"])
        self.assertEqual(self.read_result()["desktop"], {"mode": "local"})

    def test_retired_options_are_removed_without_deleting_unowned_children(self):
        self.seed_local('''model = "new-model"
service_tier = "priority"
[features.context_management]
experimental_mode = true
local_setting = "preserve"
''')
        self.assertEqual(self.install(), 3)
        self.assertEqual(self.install(force=True), 0)
        result = self.read_result()
        self.assertNotIn("service_tier", result)
        self.assertEqual(result["features"]["context_management"], {"local_setting": "preserve"})

    def test_empty_retired_table_is_pruned(self):
        self.seed_local('model = "new-model"\n[features.context_management]\nexperimental_mode = true\n')
        self.assertEqual(self.install(force=True), 0)
        self.assertNotIn("context_management", self.read_result()["features"])

    def test_explicit_overlay_can_keep_a_service_tier(self):
        self.overlay.write_text('service_tier = "fast"\n')
        self.seed_local('model = "new-model"\nservice_tier = "fast"\n[features]\nmemories = true\n')
        self.assertEqual(self.install(), 0)
        self.assertEqual(self.read_result()["service_tier"], "fast")

    def test_backup_is_exact_private_and_unchanged_install_does_not_rewrite(self):
        self.seed_local('model = "old-model"\n# preserve this in backup\n')
        original = self.destination.read_bytes()
        self.assertEqual(self.install(force=True), 0)
        backups = list(self.backup_dir.rglob("config.toml"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), original)
        self.assertEqual(stat.S_IMODE(backups[0].stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.destination.stat().st_mode), 0o600)
        previous_mtime = self.destination.stat().st_mtime_ns
        self.assertEqual(self.install(force=True), 0)
        self.assertEqual(self.destination.stat().st_mtime_ns, previous_mtime)

    def test_backup_collision_fails_without_overwriting_either_file(self):
        self.seed_local('model = "old-model"\n')
        self.assertEqual(self.install(force=True), 0)
        backup = next(self.backup_dir.rglob("config.toml"))
        backup_content = backup.read_bytes()
        self.seed_local('model = "another-local-model"\n')
        original = self.destination.read_bytes()
        with self.assertRaises(FileExistsError):
            self.install(force=True)
        self.assertEqual(self.destination.read_bytes(), original)
        self.assertEqual(backup.read_bytes(), backup_content)

    def test_invalid_toml_fails_before_writing(self):
        for broken_path in (self.destination, self.template, self.overlay):
            with self.subTest(path=broken_path):
                self.seed_local('model = "local-model"\n')
                self.template.write_text('model = "new-model"\n')
                self.overlay.unlink(missing_ok=True)
                broken_path.write_text('model = "unterminated\n')
                original = self.destination.read_bytes()
                with self.assertRaises(tomllib.TOMLDecodeError):
                    self.install(force=True)
                self.assertEqual(self.destination.read_bytes(), original)
                self.assertFalse(self.backup_dir.exists())

    def test_local_overlay_overrides_matching_template_keys(self):
        self.overlay.write_text('model = "local-model"\n[features]\nfast_mode = true\n')
        self.assertEqual(self.install(), 0)
        self.assertEqual(self.read_result()["model"], "local-model")
        self.assertEqual(self.read_result()["features"], {"memories": True, "fast_mode": True})

    def test_duplicate_tables_within_a_source_are_rejected(self):
        self.overlay.write_text('[features]\nfast_mode = true\n[features]\nmemories = false\n')
        with self.assertRaises(tomllib.TOMLDecodeError):
            self.install(force=True)
        self.assertFalse(self.destination.exists())

    def test_unowned_toml_types_survive_round_trip(self):
        self.seed_local('''model = "old-model"
[[hooks.Stop]]
matcher = "*"
hooks = [{type = "command", command = "echo \\\"ok\\\"", timeout = 10}]
["custom.table"]
"quoted.key" = "繁體中文\\nnext line"
values = [true, 5, -0.5, [1, 2]]
when = 2026-10-26T12:00:00+08:00
day = 2026-10-26
time = 12:30:00
''')
        original = self.read_result()
        self.assertIsInstance(original["custom.table"]["when"], datetime.datetime)
        self.assertEqual(self.install(force=True), 0)
        result = self.read_result()
        self.assertEqual(result["hooks"], original["hooks"])
        self.assertEqual(result["custom.table"], original["custom.table"])

    def test_concurrent_destination_change_is_not_overwritten(self):
        self.seed_local('model = "old-model"\n')
        original_read = Path.read_text
        destination_reads = 0

        def read_with_app_update(path, *arguments, **keywords):
            nonlocal destination_reads
            if path == self.destination:
                destination_reads += 1
                if destination_reads == 2:
                    path.write_text('model = "app-updated"\n')
            return original_read(path, *arguments, **keywords)

        with patch.object(Path, "read_text", read_with_app_update):
            with self.assertRaisesRegex(RuntimeError, "destination changed"):
                self.install(force=True)
        self.assertEqual(self.read_result()["model"], "app-updated")
        self.assertEqual(list(self.destination.parent.glob(".config-merge-*")), [])

    def test_cli_reports_invalid_config_as_failure(self):
        self.seed_local('model = "unterminated\n')
        result = subprocess.run(
            [sys.executable, str(SCRIPT), str(self.template), str(self.overlay), str(self.destination), str(self.backup_dir), "--force"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("error:", result.stderr)


if __name__ == "__main__":
    unittest.main()
