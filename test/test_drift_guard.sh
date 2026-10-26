#!/bin/sh
# 驗證 install.sh drift guard:預設不覆蓋 drifted dst、--force 才覆蓋。
set -eu

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
fake_home=$(mktemp -d)
trap 'rm -rf "$fake_home"' EXIT

# 首次安裝:乾淨,所有 dst 不存在 → 正常安裝
HOME="$fake_home" sh "$repo_dir/install.sh" >/dev/null 2>&1

fail=0

python3 - "$fake_home/.codex/config.toml" <<'PY'
from pathlib import Path
import re
import sys

config = Path(sys.argv[1])
text = re.sub(r'^model = .*$', 'model = "local-model"', config.read_text(), count=1, flags=re.MULTILINE)
text = 'notify = ["/local/notify", "turn-ended"]\n' + text
text += '\n[desktop]\nfollowUpQueueMode = "steer"\n'
text += '\n[mcp_servers.node_repl]\ncommand = "/local/node_repl"\n'
text += '\n[plugins."browser@bundled"]\nenabled = true\n'
text += '\n[marketplaces.bundled]\nsource_type = "local"\nsource = "/local/bundled"\n'
config.write_text(text)
PY

# 製造 drift:本機編輯一個 guarded 檔(CLAUDE.md)與一個 exempt 目標(approved memory)
echo "LOCAL EDIT MARKER" >> "$fake_home/.claude/CLAUDE.md"
echo "LOCAL EDIT MARKER" >> "$fake_home/.claude/docs/memories/approved/preferences.md"

# 第二次安裝(無 --force):
#   - CLAUDE.md(guard):skip、保留本機編輯、輸出 drift 警告
#   - approved memory(overwrite 豁免):直接覆蓋、本機編輯消失,不需 --force
out=$(HOME="$fake_home" sh "$repo_dir/install.sh" 2>&1 || true)
grep -q "LOCAL EDIT MARKER" "$fake_home/.claude/CLAUDE.md" || { echo "FAIL: drift guard overwrote local edit without --force"; fail=1; }
printf '%s\n' "$out" | grep -qi "drift" || { echo "FAIL: no drift warning emitted"; fail=1; }
grep -q 'model = "local-model"' "$fake_home/.codex/config.toml" || { echo "FAIL: codex managed conflict overwritten without --force"; fail=1; }
if grep -q "LOCAL EDIT MARKER" "$fake_home/.claude/docs/memories/approved/preferences.md"; then echo "FAIL: approved memory not exempt from drift guard (still drifted without --force)"; fail=1; fi

# 第三次安裝(--force):應覆蓋、本機編輯消失
HOME="$fake_home" sh "$repo_dir/install.sh" --force >/dev/null 2>&1
if grep -q "LOCAL EDIT MARKER" "$fake_home/.claude/CLAUDE.md"; then echo "FAIL: --force did not overwrite drifted file"; fail=1; fi

python3 - "$fake_home/.codex/config.toml" "$repo_dir" <<'PY' || fail=1
from pathlib import Path
import sys
import tomllib

config = tomllib.loads(Path(sys.argv[1]).read_text())
repo = Path(sys.argv[2])
source = tomllib.loads((repo / "codex/config.toml.template").read_text())
overlay = repo / "codex/config.local.toml"
local = tomllib.loads(overlay.read_text()) if overlay.exists() else {}
assert config["model"] == local.get("model", source["model"]), "managed model not updated"
assert config["notify"] == ["/local/notify", "turn-ended"], "App notification command lost"
assert config["desktop"] == {"followUpQueueMode": "steer"}, "App settings lost"
assert config["mcp_servers"]["node_repl"] == {"command": "/local/node_repl"}, "App MCP lost"
assert config["plugins"]["browser@bundled"]["enabled"] is True, "bundled plugin lost"
assert config["marketplaces"]["bundled"]["source"] == "/local/bundled", "bundled marketplace lost"
assert "service_tier" not in config, "retired service tier default retained"
assert "context_management" not in config.get("features", {}), "unavailable feature retained"
PY

# 未知參數應以 exit 2 拒絕
if HOME="$fake_home" sh "$repo_dir/install.sh" --bogus >/dev/null 2>&1; then echo "FAIL: unknown arg not rejected"; fail=1; fi

[ "$fail" -eq 0 ] && echo "PASS: drift guard behaves correctly"
exit "$fail"
