#!/usr/bin/env python3
"""Merge managed Codex settings while preserving keys owned by local clients."""

import argparse
import copy
import datetime
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import tomllib


REMOVED_KEYS = (
    ("service_tier",),
    ("features", "context_management", "experimental_mode"),
)


def merge_values(local, managed):
    merged = copy.deepcopy(local)
    for key, value in managed.items():
        if isinstance(value, dict):
            existing = merged.get(key, {})
            merged[key] = merge_values(existing if isinstance(existing, dict) else {}, value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def remove_key(config, path):
    key = path[0]
    if len(path) == 1:
        config.pop(key, None)
    elif isinstance(config.get(key), dict):
        remove_key(config[key], path[1:])
        if not config[key]:
            del config[key]


def has_key(config, path):
    for key in path:
        if not isinstance(config, dict) or key not in config:
            return False
        config = config[key]
    return True


def managed_conflicts(local, managed, prefix=()):
    conflicts = []
    for key, value in managed.items():
        if key not in local:
            continue
        path = prefix + (key,)
        if isinstance(value, dict) and isinstance(local[key], dict):
            conflicts.extend(managed_conflicts(local[key], value, path))
        elif local[key] != value:
            conflicts.append(".".join(path))
    return conflicts


def toml_key(key):
    return key if re.fullmatch(r"[A-Za-z0-9_-]+", key) else json.dumps(key, ensure_ascii=False)


def toml_value(value):
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, list):
        return "[" + ", ".join(toml_value(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{toml_key(key)} = {toml_value(item)}" for key, item in value.items()) + " }"
    raise ValueError(f"unsupported TOML value type: {type(value).__name__}")


def dump_toml(config, prefix=()):
    lines = []
    if prefix:
        lines.append("[" + ".".join(toml_key(key) for key in prefix) + "]")
    for key, value in config.items():
        if not isinstance(value, dict):
            lines.append(f"{toml_key(key)} = {toml_value(value)}")
    for key, value in config.items():
        if isinstance(value, dict):
            lines.extend(("", dump_toml(value, prefix + (key,)).rstrip()))
    return "\n".join(lines).lstrip("\n") + "\n"


def install(template, overlay, destination, backup_dir, force=False):
    managed = tomllib.loads(template.read_text(encoding="utf-8"))
    if overlay.exists():
        managed = merge_values(managed, tomllib.loads(overlay.read_text(encoding="utf-8")))
    existed = destination.exists()
    original_text = destination.read_text(encoding="utf-8") if existed else ""
    local = tomllib.loads(original_text)
    merged = copy.deepcopy(local)
    for path in REMOVED_KEYS:
        if not has_key(managed, path):
            remove_key(merged, path)
    removed = merged != local
    merged = merge_values(merged, managed)
    conflicts = managed_conflicts(local, managed)
    if existed and not force and (conflicts or removed):
        print(f"DRIFT: {destination} has conflicting managed settings; skipped (re-run with --force)", file=sys.stderr)
        return 3
    if merged == local:
        print(f"codex config unchanged: {destination}")
        return 0
    rendered = dump_toml(merged)
    if tomllib.loads(rendered) != merged:
        raise ValueError("TOML serialization changed configuration values")
    mode = stat.S_IMODE(destination.stat().st_mode) if existed else 0o600
    if existed:
        try:
            relative_path = destination.resolve().relative_to(Path.home().resolve())
        except ValueError:
            relative_path = Path(destination.name)
        backup = backup_dir / relative_path
        backup.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        backup_fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(backup_fd, "w", encoding="utf-8") as stream:
            stream.write(original_text)
        os.chmod(backup, mode)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_fd, temporary_path = tempfile.mkstemp(dir=destination.parent, prefix=".config-merge-")
    try:
        with os.fdopen(temporary_fd, "w", encoding="utf-8") as stream:
            stream.write(rendered)
            os.fchmod(stream.fileno(), mode)
        if destination.exists() != existed or (existed and destination.read_text(encoding="utf-8") != original_text):
            raise RuntimeError("destination changed during merge; retry without closing the app")
        os.replace(temporary_path, destination)
    finally:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)
    print(f"installed {destination} (managed keys merged; local-only keys preserved)")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("template", type=Path)
    parser.add_argument("overlay", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("backup_dir", type=Path)
    parser.add_argument("--force", action="store_true")
    arguments = parser.parse_args()
    try:
        return install(arguments.template, arguments.overlay, arguments.destination, arguments.backup_dir, arguments.force)
    except (OSError, ValueError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
