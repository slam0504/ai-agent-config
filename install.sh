#!/bin/sh
set -eu

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
backup_dir="$HOME/.ai-agent-config-backup/$(date +%Y%m%d-%H%M%S)"

copy_with_backup() {
  src="$1"
  dst="$2"

  if [ ! -f "$src" ]; then
    echo "missing source: $src" >&2
    exit 1
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

  if [ -e "$dst" ]; then
    mkdir -p "$backup_dir/$(dirname "${dst#$HOME/}")"
    cp -R "$dst" "$backup_dir/${dst#$HOME/}"
    rm -rf "$dst"
  fi

  mkdir -p "$(dirname "$dst")"
  cp -R "$src" "$dst"
  echo "installed $dst"
}

copy_with_backup "$repo_dir/codex/AGENTS.md" "$HOME/.codex/AGENTS.md"
copy_with_backup "$repo_dir/codex/config.toml" "$HOME/.codex/config.toml"
copy_with_backup "$repo_dir/claude/CLAUDE.md" "$HOME/.claude/CLAUDE.md"
copy_dir_with_backup "$repo_dir/codex/skills/distill" "$HOME/.agents/skills/distill"
copy_dir_with_backup "$repo_dir/memories/approved" "$HOME/.codex/docs/memories/approved"

if [ -d "${backup_dir%/*}" ] && [ -d "$backup_dir" ]; then
  echo "backup: $backup_dir"
fi
