#!/usr/bin/env bash
# gemini-bridge.sh — read-only Gemini call wrapper for use as a Claude sub-agent consultant.
#
# Contract (see ~/.claude/plans/claude-gemini-cluade-snoopy-melody.md):
#   Usage: gemini-bridge.sh [--model <m>] [--cwd <dir>] -- <prompt...>
#   - Always runs Gemini read-only: --approval-mode plan --skip-trust.
#   - Binary is hardcoded (no env override) so callers cannot redirect it.
#   - --cwd sets Gemini's read workspace; sensitive trees are mechanically denied.
#   - Without --cwd, runs in a throwaway empty dir (minimal read exposure).
#   - stdout = gemini stdout; stderr = gemini stderr; exit code propagated.
#   - usage errors go to stderr, keep stdout empty, exit non-zero.
#
# bash 3.2 compatible (macOS system bash). Do not use 4.0+ features.

# Production binary: hardcoded literal, NO env fallback (zero override surface).
# Deterministic tests operate on a sed'd copy of this file, not via env.
GEMINI_BIN=/usr/local/bin/gemini

usage() {
  cat >&2 <<'EOF'
usage: gemini-bridge.sh [--model <m>] [--cwd <dir>] -- <prompt...>
  --model <m>   model name (overrides $GEMINI_MODEL); optional
  --cwd <dir>   Gemini read workspace (existing dir, not a sensitive tree); optional
  --            separator; everything after it is the prompt
Always runs Gemini read-only (--approval-mode plan --skip-trust).
EOF
}

# usage_err <msg>: print message + usage to stderr, exit non-zero, leave stdout clean.
usage_err() {
  echo "gemini-bridge: $1" >&2
  usage
  exit 2
}

MODEL_FLAG=""
CWD=""
saw_dashdash=0

while [ $# -gt 0 ]; do
  case "$1" in
    --model)
      [ $# -ge 2 ] || usage_err "--model requires a value"
      MODEL_FLAG="$2"
      shift 2
      ;;
    --cwd)
      [ $# -ge 2 ] || usage_err "--cwd requires a value"
      CWD="$2"
      shift 2
      ;;
    --)
      saw_dashdash=1
      shift
      break
      ;;
    *)
      usage_err "unexpected argument before --: $1"
      ;;
  esac
done

[ "$saw_dashdash" -eq 1 ] || usage_err "missing -- separator"

# Join all remaining args into a single prompt with single spaces.
prompt="$*"
[ -n "$prompt" ] || usage_err "empty prompt"

# Resolve model precedence: --model flag > $GEMINI_MODEL env > unset.
model=""
if [ -n "$MODEL_FLAG" ]; then
  model="$MODEL_FLAG"
elif [ -n "${GEMINI_MODEL:-}" ]; then
  model="$GEMINI_MODEL"
fi

# Verify the pinned binary is executable.
[ -x "$GEMINI_BIN" ] || usage_err "gemini binary not executable: $GEMINI_BIN"

# Determine working directory (Gemini's read workspace).
if [ -n "$CWD" ]; then
  [ -e "$CWD" ] || usage_err "--cwd does not exist: $CWD"
  [ -d "$CWD" ] || usage_err "--cwd is not a directory: $CWD"

  rp_cwd="$(realpath "$CWD" 2>/dev/null)" || usage_err "--cwd cannot be resolved: $CWD"
  rp_home="$(realpath "$HOME" 2>/dev/null)"

  # Reject root and $HOME itself (exact).
  if [ "$rp_cwd" = "/" ] || [ "$rp_cwd" = "$rp_home" ]; then
    usage_err "--cwd refused (sensitive path): $CWD"
  fi
  # Reject sensitive trees and all descendants (segment-aware prefix match).
  for blocked in "$rp_home/.ssh" "$rp_home/.claude" "$rp_home/.gemini"; do
    case "$rp_cwd" in
      "$blocked"|"$blocked"/*)
        usage_err "--cwd refused (sensitive tree): $CWD"
        ;;
    esac
  done

  cd "$rp_cwd" || usage_err "--cwd cannot be entered: $CWD"
else
  tmpcwd="$(mktemp -d)" || usage_err "cannot create temp workspace"
  chmod 700 "$tmpcwd"
  trap 'rm -rf "$tmpcwd"' EXIT
  cd "$tmpcwd" || usage_err "cannot enter temp workspace"
fi

# Build argv as an array (no eval, no string-built shell) to neutralize
# any shell metacharacters in prompt/model/cwd values.
args=(-p "$prompt" --approval-mode plan --skip-trust)
if [ -n "$model" ]; then
  args+=(--model "$model")
fi

# Run Gemini. stdout->stdout, stderr->stderr inherited; propagate exit code.
"$GEMINI_BIN" "${args[@]}"
exit $?
