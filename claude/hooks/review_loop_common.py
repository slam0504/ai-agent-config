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


# Per-file and total caps on how many bytes of untracked-file content get
# hashed/embedded. On a repo with no .gitignore and huge untracked trees
# (node_modules, build output) reading every byte of every untracked file
# made the Stop hook slow and the review packet enormous. Overridable via env
# so tests (and users) can tune without editing code; read at call time via
# current_untracked_limits(), not frozen into a constant, so an env override
# set after import still takes effect.
UNTRACKED_FILE_LIMIT_BYTES = 1024 * 1024  # 1 MiB, per file
UNTRACKED_TOTAL_LIMIT_BYTES = 8 * 1024 * 1024  # 8 MiB, summed over all untracked files


def current_untracked_limits():
    """Return (file_limit_bytes, total_limit_bytes), honoring env overrides."""
    return (
        get_int("RL_UNTRACKED_FILE_LIMIT", UNTRACKED_FILE_LIMIT_BYTES),
        get_int("RL_UNTRACKED_TOTAL_LIMIT", UNTRACKED_TOTAL_LIMIT_BYTES),
    )


def _untracked_scan(root, collect_content=False):
    """One pass over untracked files producing fp parts, a status dict, and
    (when collect_content) the raw bytes of every fully-read file.

    Iterates paths in sorted order for determinism. Never trusts os.stat for
    sizing (a file can grow between stat and read — TOCTOU): every file is
    opened and read with an explicit bound, `read(cap + 1)`, where `cap` is
    whatever's left of both the per-file limit and the remaining total
    budget. Reading one byte past `cap` is enough to prove the file doesn't
    fit without ever reading (or hashing) more than that.

    A file whose bounded read comes back bigger than the per-file limit is
    over-limit and not hashed; it contributes "{rel}:<over-limit:{file_limit}>"
    (the limit, not a discovered size — the whole point is that we never
    learn or trust the true size) so the fingerprint still reacts to a
    rename but not to a content edit that stays over the same limit. A file
    that fits the per-file limit but would push the cumulative read past the
    total limit is left unread instead, and once that happens no further
    files are read: each remaining path (including the one that tipped the
    total) contributes just its (unhashed) name — so a path change still
    alters the fingerprint — followed by one final summary part. A read that
    fails outright (permissions, races, ...) is recorded as unreadable.

    collect_content=True additionally returns the exact bytes read for every
    fully-read file, keyed by rel path — so a second consumer (the review
    packet, which needs the actual content, not just a hash) can reuse this
    pass's bytes instead of re-opening the file with an unbounded read,
    which would reopen the same TOCTOU gap this function closes.

    Returns (parts, status, contents). status is
    {"complete": bool, "over_limit": [rel, ...], "unread": [rel, ...],
     "unreadable": [rel, ...]}. contents is {} unless collect_content is
    True, in which case it maps rel -> bytes for every file included in a
    "{rel}:sha256" part (i.e. every file NOT in over_limit/unread/unreadable).
    """
    file_limit, total_limit = current_untracked_limits()
    parts = []
    over_limit = []
    unread = []
    unreadable = []
    contents = {}
    total_read = 0
    stopped = False
    for rel in sorted(untracked_files(root)):
        if stopped:
            unread.append(rel)
            parts.append(rel)
            continue
        remaining_total = total_limit - total_read
        cap = min(file_limit, max(remaining_total, 0))
        path = os.path.join(root, rel)
        try:
            with open(path, "rb") as f:
                data = f.read(cap + 1)
        except OSError:
            unreadable.append(rel)
            parts.append(f"{rel}:<unreadable: {rel}>")
            continue
        if len(data) > file_limit:
            over_limit.append(rel)
            parts.append(f"{rel}:<over-limit:{file_limit}>")
            continue
        if len(data) > remaining_total:
            stopped = True
            unread.append(rel)
            parts.append(rel)
            continue
        total_read += len(data)
        parts.append(f"{rel}:{hashlib.sha256(data).hexdigest()}")
        if collect_content:
            contents[rel] = data
    if stopped:
        parts.append(f"<total-over-limit:{len(unread)} files unread>")
    status = {
        "complete": not (over_limit or unread or unreadable),
        "over_limit": over_limit,
        "unread": unread,
        "unreadable": unreadable,
    }
    return parts, status, contents


def untracked_fp_parts(root):
    """Per-file "path:sha256(bytes)" entries for untracked files, for fingerprinting.

    Hashes raw bytes (not text-decoded content) so binary/invalid-UTF-8
    content that would collide under lossy decoding still fingerprints
    distinctly. A read failure is recorded explicitly rather than silently
    treated as empty. Files over UNTRACKED_FILE_LIMIT_BYTES, or beyond
    UNTRACKED_TOTAL_LIMIT_BYTES cumulative, are not read — see _untracked_scan.
    """
    parts, _, _ = _untracked_scan(root)
    return parts


def untracked_status(root):
    """{"complete", "over_limit", "unread", "unreadable"} for the untracked-file
    content cap.

    Computed by the same rules as untracked_fp_parts() (shared _untracked_scan
    pass), so callers can tell whether a review actually covered every
    untracked file's content. "complete" is False whenever any file was
    skipped for any reason (over the per-file limit, past the total budget,
    or unreadable) — a caller must not treat the review as full coverage
    unless "complete" is True.
    """
    _, status, _ = _untracked_scan(root)
    return status


def untracked_content(root):
    """(status, contents) from one bounded scan; contents maps rel -> bytes
    for every file that was fully read under the caps (the same files
    untracked_status() would NOT list in over_limit/unread/unreadable).

    Build the review packet's embedded content from this, not from a second
    unbounded open()+read() of each file — re-reading without a bound would
    reopen the TOCTOU gap _untracked_scan's bounded read closes (a file that
    grows between the status scan and a later full read would get fully
    embedded even though it's over limit).
    """
    _, status, contents = _untracked_scan(root, collect_content=True)
    return status, contents


def untracked_incomplete_suffix(root):
    """" (untracked content over limit: N files not fully checked)", or ""
    when untracked_status() reports complete. N counts over-limit, unread,
    and unreadable files together — all three mean the check didn't see that
    file's full content.
    """
    status = untracked_status(root)
    if status["complete"]:
        return ""
    n = len(status["over_limit"]) + len(status["unread"]) + len(status["unreadable"])
    return f" (untracked content over limit: {n} files not fully checked)"


def tree_dirty(root):
    rc1, _ = run_git(root, ["diff", "--quiet", "--", ".", ":!.agent"])
    rc2, _ = run_git(root, ["diff", "--cached", "--quiet", "--", ".", ":!.agent"])
    # --quiet exits non-zero when differences exist; untracked files never show up there.
    return rc1 != 0 or rc2 != 0 or bool(untracked_files(root))


def base_sha(root):
    rc, out = run_git(root, ["rev-parse", "HEAD"])
    return out.strip() if rc == 0 and out.strip() else "none"


def cheap_worktree_fp_and_status(root):
    """(fp, status) from a single untracked-file scan.

    A caller that needs to know whether the fp it just captured actually
    covers every untracked file's content (e.g. reviewer.cmd_prepare, which
    persists both into packet metadata) must get them from the same scan —
    two separate calls to untracked_fp_parts()/untracked_status() could in
    principle observe a different tree (a file edited in between) and
    disagree about what the fp describes.
    """
    untracked_parts, status, _ = _untracked_scan(root)
    parts = [
        base_sha(root),
        run_git(root, ["diff", "HEAD", "--", ".", ":!.agent"])[1],
        run_git(root, ["diff", "--cached", "HEAD", "--", ".", ":!.agent"])[1],
        "\n".join(untracked_parts),
    ]
    return sha12("\n".join(parts)), status


def cheap_worktree_fp(root):
    return cheap_worktree_fp_and_status(root)[0]


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
