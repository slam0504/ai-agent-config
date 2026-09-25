"""Shared helpers for review-loop hooks (stdlib only)."""
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone


def read_hook_input(raw):
    if not raw or not str(raw).strip():
        return {}
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return {}


def get_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except (ValueError, TypeError):
        return default


def resolve_project_root(data):
    return (data or {}).get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()


def rl_dir(root):
    return os.path.join(root, ".agent", "review-loop")


def is_enabled(root):
    return os.path.exists(os.path.join(rl_dir(root), "enabled"))


def truncate(text, maxchars,
             marker="\n…(truncated — full feedback at .agent/review-loop/codex-feedback.md)"):
    if text is None:
        return ""
    if len(text) <= maxchars:
        return text
    keep = max(0, maxchars - len(marker))
    return (text[:keep] + marker)[:maxchars]


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def log(root, msg):
    try:
        d = rl_dir(root)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "review-loop.log"), "a") as f:
            f.write(f"{now_iso()} {msg}\n")
    except OSError:
        pass


def atomic_write(path, content):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write(content)
    os.replace(tmp, path)


def read_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {} if default is None else default


def write_json(path, obj):
    atomic_write(path, json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def sha12(text):
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:12]


def run_git(root, args):
    """Return (returncode, stdout). Never raises."""
    try:
        p = subprocess.run(["git", "-C", root] + args,
                           capture_output=True, text=True, timeout=10)
        return p.returncode, p.stdout
    except (OSError, subprocess.SubprocessError):
        return 1, ""


def is_git_repo(root):
    rc, out = run_git(root, ["rev-parse", "--is-inside-work-tree"])
    return rc == 0 and out.strip() == "true"


def untracked_files(root):
    """Non-ignored untracked file paths (relative to root), excluding .agent.

    Uses -z (NUL-separated, unquoted) output: without it, git quotes
    non-ASCII paths (e.g. `"\\346\\270\\254...\\.py"`) under core.quotePath,
    which then fail to open() and silently look empty/absent.
    """
    try:
        p = subprocess.run(
            ["git", "-C", root, "ls-files", "-z", "--others", "--exclude-standard",
             "--", ".", ":!.agent"],
            capture_output=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if p.returncode != 0:
        return []
    return [b.decode("utf-8", "surrogateescape") for b in p.stdout.split(b"\0") if b]


def untracked_fp_parts(root):
    """Per-file "path:sha256(bytes)" entries for untracked files, for fingerprinting.

    Hashes raw bytes (not text-decoded content) so binary/invalid-UTF-8
    content that would collide under lossy decoding still fingerprints
    distinctly. A read failure is recorded explicitly rather than silently
    treated as empty.
    """
    parts = []
    for rel in untracked_files(root):
        try:
            with open(os.path.join(root, rel), "rb") as f:
                data = f.read()
        except OSError:
            parts.append(f"{rel}:<unreadable: {rel}>")
            continue
        parts.append(f"{rel}:{hashlib.sha256(data).hexdigest()}")
    return parts


def tree_dirty(root):
    rc1, _ = run_git(root, ["diff", "--quiet", "--", ".", ":!.agent"])
    rc2, _ = run_git(root, ["diff", "--cached", "--quiet", "--", ".", ":!.agent"])
    # --quiet exits non-zero when differences exist; untracked files never show up there.
    return rc1 != 0 or rc2 != 0 or bool(untracked_files(root))


def base_sha(root):
    rc, out = run_git(root, ["rev-parse", "HEAD"])
    return out.strip() if rc == 0 and out.strip() else "none"


def cheap_worktree_fp(root):
    parts = [
        base_sha(root),
        run_git(root, ["diff", "HEAD", "--", ".", ":!.agent"])[1],
        run_git(root, ["diff", "--cached", "HEAD", "--", ".", ":!.agent"])[1],
        "\n".join(untracked_fp_parts(root)),
    ]
    return sha12("\n".join(parts))


STATE_DEFAULTS = {
    "iteration": 0,
    "max_iterations": 5,
    "last_verdict": None,
    "last_consumed_feedback_hash": None,
    "done": False,
}


def read_state(root):
    state = dict(STATE_DEFAULTS)
    state["max_iterations"] = get_int("RL_MAX_ITERATIONS", 5)
    state.update(read_json(os.path.join(rl_dir(root), "state.json"), {}))
    return state


def write_state(root, state):
    write_json(os.path.join(rl_dir(root), "state.json"), state)


def parse_feedback_header(md):
    """Return (header_dict, body) for a leading --- ... --- block."""
    if not md.startswith("---"):
        return {}, md
    end = md.find("\n---", 3)
    if end == -1:
        return {}, md
    header = {}
    for line in md[3:end].strip().splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            header[k.strip()] = v.strip()
    body = md[end + 4:].lstrip("\n")
    return header, body
