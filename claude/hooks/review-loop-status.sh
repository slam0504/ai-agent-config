#!/usr/bin/env bash
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if python3 "$DIR/sessionstart_status.py"; then
  exit 0
else
  rc=$?
fi
[ "${RL_STRICT:-}" = "1" ] && exit "$rc"
exit 0
