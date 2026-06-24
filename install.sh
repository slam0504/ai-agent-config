#!/bin/sh
set -eu

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
backup_dir="$HOME/.ai-agent-config-backup/$(date +%Y%m%d-%H%M%S)"

# Drift guard: by default, refuse to overwrite a destination that differs from
# the repo source (it may hold un-synced local edits). Re-run with --force to
# overwrite (a backup is still taken). Skipped files are summarised at the end.
force=0
for arg in "$@"; do
  case "$arg" in
    --force) force=1 ;;
    *) echo "unknown argument: $arg (supported: --force)" >&2; exit 2 ;;
  esac
done
skipped=""

copy_with_backup() {
  src="$1"
  dst="$2"

  if [ ! -f "$src" ]; then
    echo "missing source: $src" >&2
    exit 1
  fi

  if [ -e "$dst" ] && [ "$force" -eq 0 ] && ! diff -q "$src" "$dst" >/dev/null 2>&1; then
    echo "DRIFT: $dst differs from repo source; skipped (re-run with --force)" >&2
    skipped="$skipped $dst"
    return 0
  fi

  if [ -e "$dst" ]; then
    mkdir -p "$backup_dir/$(dirname "${dst#$HOME/}")"
    cp "$dst" "$backup_dir/${dst#$HOME/}"
  fi

  mkdir -p "$(dirname "$dst")"
  cp "$src" "$dst"
  echo "installed $dst"
}

copy_dir_with_backup() {
  src="$1"
  dst="$2"

  if [ ! -d "$src" ]; then
    echo "missing source directory: $src" >&2
    exit 1
  fi

  if [ -e "$dst" ] && [ "$force" -eq 0 ] && ! diff -rq "$src" "$dst" >/dev/null 2>&1; then
    echo "DRIFT: $dst differs from repo source; skipped (re-run with --force)" >&2
    skipped="$skipped $dst"
    return 0
  fi

  if [ -e "$dst" ]; then
    mkdir -p "$backup_dir/$(dirname "${dst#$HOME/}")"
    cp -R "$dst" "$backup_dir/${dst#$HOME/}"
    rm -rf "$dst"
  fi

  mkdir -p "$(dirname "$dst")"
  cp -R "$src" "$dst"
  echo "installed $dst"
}

# Build ~/.codex/config.toml from the portable template plus an optional,
# machine-specific overlay (codex/config.local.toml, gitignored). Keeps absolute
# project paths and trust state out of the synced repo.
build_codex_config() {
  template="$repo_dir/codex/config.toml.template"
  overlay="$repo_dir/codex/config.local.toml"
  dst="$HOME/.codex/config.toml"

  if [ ! -f "$template" ]; then
    echo "missing source: $template" >&2
    exit 1
  fi

  # Assemble the desired config into a temp file first, so the drift guard can
  # compare the assembled result (not a single source file) against the dst.
  tmp=$(mktemp)
  cat "$template" > "$tmp"
  if [ -f "$overlay" ]; then
    printf '\n' >> "$tmp"
    cat "$overlay" >> "$tmp"
  fi

  if [ -e "$dst" ] && [ "$force" -eq 0 ] && ! diff -q "$tmp" "$dst" >/dev/null 2>&1; then
    echo "DRIFT: $dst differs from assembled config; skipped (re-run with --force)" >&2
    skipped="$skipped $dst"
    rm -f "$tmp"
    return 0
  fi

  if [ -e "$dst" ]; then
    mkdir -p "$backup_dir/$(dirname "${dst#$HOME/}")"
    cp "$dst" "$backup_dir/${dst#$HOME/}"
  fi

  mkdir -p "$(dirname "$dst")"
  cp "$tmp" "$dst"
  rm -f "$tmp"
  if [ -f "$overlay" ]; then
    echo "installed $dst (template + local overlay)"
  else
    echo "installed $dst (template only — no codex/config.local.toml)"
  fi
}

copy_with_backup "$repo_dir/codex/AGENTS.md" "$HOME/.codex/AGENTS.md"
build_codex_config
copy_with_backup "$repo_dir/claude/CLAUDE.md" "$HOME/.claude/CLAUDE.md"
copy_dir_with_backup "$repo_dir/codex/skills/distill" "$HOME/.agents/skills/distill"
copy_dir_with_backup "$repo_dir/memories/approved" "$HOME/.codex/docs/memories/approved"
copy_dir_with_backup "$repo_dir/claude/skills/distill" "$HOME/.claude/skills/distill"
copy_dir_with_backup "$repo_dir/memories/approved" "$HOME/.claude/docs/memories/approved"

if [ -d "${backup_dir%/*}" ] && [ -d "$backup_dir" ]; then
  echo "backup: $backup_dir"
fi

if [ -n "$skipped" ]; then
  echo "" >&2
  echo "drift guard skipped (edit the repo source to keep changes, or re-run with --force to overwrite):" >&2
  for f in $skipped; do
    echo "  - $f" >&2
  done
fi
