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

  if [ -e "$dst" ]; then
    mkdir -p "$backup_dir/$(dirname "${dst#$HOME/}")"
    cp "$dst" "$backup_dir/${dst#$HOME/}"
  fi

  mkdir -p "$(dirname "$dst")"
  cat "$template" > "$dst"
  if [ -f "$overlay" ]; then
    printf '\n' >> "$dst"
    cat "$overlay" >> "$dst"
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
