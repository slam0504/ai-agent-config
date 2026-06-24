#!/bin/sh
# 驗證 install.sh drift guard:預設不覆蓋 drifted dst、--force 才覆蓋。
set -eu

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
fake_home=$(mktemp -d)
trap 'rm -rf "$fake_home"' EXIT

# 首次安裝:乾淨,所有 dst 不存在 → 正常安裝
HOME="$fake_home" sh "$repo_dir/install.sh" >/dev/null 2>&1

fail=0

# 製造 drift:本機編輯一個已同步檔
echo "LOCAL EDIT MARKER" >> "$fake_home/.claude/CLAUDE.md"

# 第二次安裝(無 --force):應 skip CLAUDE.md、保留本機編輯、輸出 drift 警告
out=$(HOME="$fake_home" sh "$repo_dir/install.sh" 2>&1 || true)
grep -q "LOCAL EDIT MARKER" "$fake_home/.claude/CLAUDE.md" || { echo "FAIL: drift guard overwrote local edit without --force"; fail=1; }
printf '%s\n' "$out" | grep -qi "drift" || { echo "FAIL: no drift warning emitted"; fail=1; }

# 第三次安裝(--force):應覆蓋、本機編輯消失
HOME="$fake_home" sh "$repo_dir/install.sh" --force >/dev/null 2>&1
if grep -q "LOCAL EDIT MARKER" "$fake_home/.claude/CLAUDE.md"; then echo "FAIL: --force did not overwrite drifted file"; fail=1; fi

# 未知參數應以 exit 2 拒絕
if HOME="$fake_home" sh "$repo_dir/install.sh" --bogus >/dev/null 2>&1; then echo "FAIL: unknown arg not rejected"; fail=1; fi

[ "$fail" -eq 0 ] && echo "PASS: drift guard behaves correctly"
exit "$fail"
