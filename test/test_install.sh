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

[ "$fail" -eq 0 ] && echo "PASS: install sync boundaries correct"
exit "$fail"
