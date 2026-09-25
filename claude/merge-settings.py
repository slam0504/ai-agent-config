#!/usr/bin/env python3
"""Merge the repo's Claude Code settings.json into a local ~/.claude/settings.json.

Claude Code only has a single user-level settings.json, so the repo's
managed settings must be merged into it instead of overwriting the whole
file (which would clobber local-only permissions.allow entries, hooks from
other tools, env, etc).

Usage:
    python3 claude/merge-settings.py <repo-settings.json> <dest> <backup-dir>

Merge rules (see claude/review/2026-09-25/README.md for the design discussion):

- Managed keys: every top-level key in the repo file except "permissions"
  and "hooks". Scalars are replaced by the repo value. Dict-valued keys are
  shallow-unioned (repo entries win, local-only entries preserved).
- "permissions": only the keys present in the repo's permissions object are
  set (currently just "defaultMode"); every other local key (allow, deny,
  ask, additionalDirectories, ...) is left untouched.
- "hooks": for each event/group in the repo, look at every local group for
  that event with the same matcher (a missing matcher and "" are distinct;
  there can be more than one such group locally). A repo command already
  present — in path-normalised form — in any of those groups is not added
  again. Anything genuinely new is appended to the first such group (or the
  whole repo group is appended if no local group with that matcher exists).
  Local-only events/groups/commands are never touched, removed, or reordered.
- Any local top-level key absent from the repo file (e.g. "env") is kept.
"""
import copy
import json
import os
import re
import sys

_MISSING = object()
_WHITESPACE_RE = re.compile(r"\s+")


def matcher_key(group):
    """Return a hashable/comparable key for a hook group's matcher, treating
    a missing matcher and an empty-string matcher as distinct values."""
    if "matcher" not in group:
        return (False, None)
    return (True, group["matcher"])


def normalize_command(command):
    """Normalise a hook command string for equivalence comparison only —
    never used for the text actually stored. Expands $HOME/${HOME}/leading
    ~ to the real home directory (os.path.expanduser honours the HOME env
    var, so this works under a fake HOME in tests) and collapses whitespace,
    so e.g. `bash "$HOME/x.sh"` and `bash "/Users/eason/x.sh"` compare equal."""
    if not command:
        return command
    home = os.path.expanduser("~")
    normalized = command.replace("${HOME}", home).replace("$HOME", home)
    if normalized.startswith("~"):
        normalized = home + normalized[1:]
    return _WHITESPACE_RE.sub(" ", normalized).strip()


def merge_managed_value(repo_value, local_value):
    if isinstance(repo_value, dict):
        merged = dict(local_value) if isinstance(local_value, dict) else {}
        merged.update(repo_value)
        return merged
    return repo_value


def merge_permissions(repo_permissions, local_permissions):
    merged = dict(local_permissions) if isinstance(local_permissions, dict) else {}
    for key, value in repo_permissions.items():
        merged[key] = value
    return merged


def merge_hooks(repo_hooks, local_hooks):
    merged = copy.deepcopy(local_hooks) if isinstance(local_hooks, dict) else {}
    changed_events = []

    for event, repo_groups in repo_hooks.items():
        local_groups = merged.setdefault(event, [])
        event_changed = False

        for repo_group in repo_groups:
            same_matcher_groups = [
                g for g in local_groups if matcher_key(g) == matcher_key(repo_group)
            ]

            if not same_matcher_groups:
                local_groups.append(copy.deepcopy(repo_group))
                event_changed = True
                continue

            existing_commands = {
                normalize_command(entry.get("command"))
                for g in same_matcher_groups
                for entry in g.get("hooks", [])
            }
            target = same_matcher_groups[0]
            target.setdefault("hooks", [])
            for entry in repo_group.get("hooks", []):
                normalized = normalize_command(entry.get("command"))
                if normalized not in existing_commands:
                    target["hooks"].append(copy.deepcopy(entry))
                    existing_commands.add(normalized)
                    event_changed = True

        if event_changed:
            changed_events.append(event)

    return merged, changed_events


def backup_path_for(dest_abs, backup_dir):
    home = os.environ.get("HOME", "")
    if home:
        home_prefix = home.rstrip(os.sep) + os.sep
        if dest_abs.startswith(home_prefix):
            rel = dest_abs[len(home_prefix):]
            return os.path.join(backup_dir, rel)
    return os.path.join(backup_dir, os.path.basename(dest_abs))


def main(argv):
    if len(argv) != 4:
        print(
            "usage: merge-settings.py <repo-settings.json> <dest> <backup-dir>",
            file=sys.stderr,
        )
        return 2

    repo_path, dest_path, backup_dir = argv[1], argv[2], argv[3]

    with open(repo_path, "r", encoding="utf-8") as f:
        repo = json.load(f)

    dest_abs = os.path.abspath(dest_path)
    dest_existed = os.path.exists(dest_path)
    if dest_existed:
        try:
            with open(dest_path, "r", encoding="utf-8") as f:
                original_text = f.read()
            local = json.loads(original_text) if original_text.strip() else {}
        except (json.JSONDecodeError, OSError) as exc:
            print(f"error: invalid JSON in {dest_path}: {exc}", file=sys.stderr)
            return 2
    else:
        local = {}

    merged = copy.deepcopy(local)
    changed = []

    managed_keys = [k for k in repo.keys() if k not in ("permissions", "hooks")]
    for key in managed_keys:
        new_value = merge_managed_value(repo[key], local.get(key))
        if new_value != local.get(key, _MISSING):
            changed.append(key)
        merged[key] = new_value

    if "permissions" in repo:
        new_permissions = merge_permissions(repo["permissions"], local.get("permissions"))
        if new_permissions != local.get("permissions", _MISSING):
            changed.append("permissions")
        merged["permissions"] = new_permissions

    if "hooks" in repo:
        new_hooks, changed_events = merge_hooks(repo["hooks"], local.get("hooks"))
        merged["hooks"] = new_hooks
        changed.extend(f"hooks.{event}" for event in changed_events)

    if merged == local:
        print(f"settings unchanged: {dest_path}")
        return 0

    if dest_existed:
        backup_dest = backup_path_for(dest_abs, backup_dir)
        os.makedirs(os.path.dirname(backup_dest), exist_ok=True)
        with open(dest_path, "r", encoding="utf-8") as f:
            existing_bytes = f.read()
        with open(backup_dest, "w", encoding="utf-8") as f:
            f.write(existing_bytes)

    os.makedirs(os.path.dirname(dest_abs) or ".", exist_ok=True)
    tmp_path = dest_abs + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp_path, dest_abs)

    print(f"merged settings into {dest_path} (changed: {', '.join(changed)})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
