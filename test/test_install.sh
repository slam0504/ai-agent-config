#!/bin/sh
# 在隔離的 fake HOME 跑 install.sh,驗證只同步 approved、skill,不碰 review/secrets。
set -eu

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
fake_home=$(mktemp -d)

# 注入一個假 secret 到 review/,稍後斷言它不會被同步出去
mkdir -p "$repo_dir/memories/review"
echo "token=AKIAFAKESECRET12345" > "$repo_dir/memories/review/_test_secret.md"
cleanup() { rm -f "$repo_dir/memories/review/_test_secret.md"; rm -rf "$fake_home"; }
trap cleanup EXIT

# 預先在 fake HOME 放一個 hooks/ 本機專屬檔案(例如 wrapper 產生的 log),
# 稍後斷言 per-file 安裝不會動到它。
mkdir -p "$fake_home/.claude/hooks"
echo "local wrapper error log" > "$fake_home/.claude/hooks/.wrapper-error.log"

# 預先放一份 fake settings.json:含本機 env、permissions.allow、一個本機專屬
# 的 Stop hook,稍後斷言 merge 後這些本機內容原樣保留,repo 的 managed 值與
# hooks 則被併入。
mkdir -p "$fake_home/.claude"
cat > "$fake_home/.claude/settings.json" <<'JSON'
{
  "env": {"PATH": "/usr/local/bin:/usr/bin"},
  "language": "English",
  "permissions": {
    "defaultMode": "manual",
    "allow": ["Bash(go test:*)", "Bash(git status:*)"]
  },
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {"type": "command", "command": "/usr/local/bin/python3 /Users/x/playground/telegram/stop_hook.py"}
        ]
      }
    ]
  }
}
JSON

HOME="$fake_home" sh "$repo_dir/install.sh" >/dev/null

fail=0
[ -f "$fake_home/.claude/skills/distill/SKILL.md" ] || { echo "FAIL: claude distill skill not installed"; fail=1; }
[ -f "$fake_home/.claude/docs/memories/approved/preferences.md" ] || { echo "FAIL: claude approved memory not installed"; fail=1; }
[ ! -e "$fake_home/.claude/docs/memories/review" ] || { echo "FAIL: review/ leaked into claude"; fail=1; }
if grep -rq "AKIAFAKESECRET12345" "$fake_home" 2>/dev/null; then echo "FAIL: secret leaked into installed tree"; fail=1; fi

# F2: ~/.codex/config.toml is assembled from the portable template, and (when the
# machine overlay exists) includes its trust blocks. The tracked repo must not
# contain a monolithic codex/config.toml.
grep -q '^model = ' "$fake_home/.codex/config.toml" || { echo "FAIL: codex config missing portable template content"; fail=1; }
[ ! -f "$repo_dir/codex/config.toml" ] || { echo "FAIL: monolithic codex/config.toml still tracked in repo"; fail=1; }
if [ -f "$repo_dir/codex/config.local.toml" ]; then
  grep -q 'trust_level' "$fake_home/.codex/config.toml" || { echo "FAIL: codex config missing local overlay trust blocks"; fail=1; }
fi

# Hooks:.py/.sh 逐檔安裝、tests/ 不安裝、本機專屬檔案不受影響
[ -f "$fake_home/.claude/hooks/codex-review-plan.py" ] || { echo "FAIL: hook .py not installed"; fail=1; }
[ -f "$fake_home/.claude/hooks/review-loop-stop.sh" ] || { echo "FAIL: hook .sh not installed"; fail=1; }
[ ! -e "$fake_home/.claude/hooks/tests" ] || { echo "FAIL: hooks/tests/ leaked into install"; fail=1; }
[ -f "$fake_home/.claude/hooks/.wrapper-error.log" ] || { echo "FAIL: local-only hook file was removed"; fail=1; }
grep -q "local wrapper error log" "$fake_home/.claude/hooks/.wrapper-error.log" || { echo "FAIL: local-only hook file was overwritten"; fail=1; }

# Agents:/Users/example 換成 fake HOME,且沒有殘留
grep -q "$fake_home/.claude/agent-memory/code-inspector" "$fake_home/.claude/agents/code-inspector.md" || { echo "FAIL: agent-memory path not substituted"; fail=1; }
if grep -q "/Users/example" "$fake_home/.claude/agents/code-inspector.md" "$fake_home/.claude/agents/devcontainer-test-runner.md"; then
  echo "FAIL: /Users/example placeholder leaked into installed agents"; fail=1
fi

# Scripts:gemini-bridge.sh 安裝且保留可執行權限
[ -x "$fake_home/.claude/scripts/gemini-bridge.sh" ] || { echo "FAIL: gemini-bridge.sh not installed executable"; fail=1; }

# Skill:commit-ready 安裝
[ -f "$fake_home/.claude/skills/commit-ready/SKILL.md" ] || { echo "FAIL: commit-ready skill not installed"; fail=1; }

# Settings:merge 而非整檔覆蓋 — repo 的 managed 值/hooks 併入,本機 allow 與
# Stop hook 原樣保留
python3 - "$fake_home/.claude/settings.json" <<'PY' || fail=1
import json, sys
with open(sys.argv[1], encoding="utf-8") as f:
    settings = json.load(f)
assert settings["language"] == "繁體中文", "language not overridden by repo"
assert settings["permissions"]["defaultMode"] == "auto", "defaultMode not overridden by repo"
assert settings["permissions"]["allow"] == ["Bash(go test:*)", "Bash(git status:*)"], "local allow list changed"
assert settings["env"] == {"PATH": "/usr/local/bin:/usr/bin"}, "local env not preserved"
assert "SessionStart" in settings["hooks"], "repo SessionStart hooks missing"
stop_commands = [h["command"] for h in settings["hooks"]["Stop"][0]["hooks"]]
assert "/usr/local/bin/python3 /Users/x/playground/telegram/stop_hook.py" in stop_commands, "local Stop hook lost"
assert any("review-loop-stop.sh" in c for c in stop_commands), "repo Stop hook not merged in"
PY
[ "$fail" -eq 0 ] || echo "FAIL: settings.json merge result incorrect"

# 第二次安裝:overwrite 目標不應出現 DRIFT,settings.json 應回報 unchanged
out2=$(HOME="$fake_home" sh "$repo_dir/install.sh" 2>&1)
if printf '%s\n' "$out2" | grep -qi "drift"; then echo "FAIL: unexpected DRIFT on second install"; fail=1; fi
printf '%s\n' "$out2" | grep -q "settings unchanged" || { echo "FAIL: settings.json not reported unchanged on second install"; fail=1; }

[ "$fail" -eq 0 ] && echo "PASS: install sync boundaries correct"
exit "$fail"
