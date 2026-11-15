"""Push anonymized play logs to the repo's `play-logs` branch.

Player names are replaced everywhere (player field, inputs, replies) with stable anonymous IDs derived from a
secret salt that stays on this machine (logs/.salt), so the published logs cannot be traced back to a name.

    python3 tools/sync_logs.py            # one sync; the server runs this every ZOAIRK_LOG_SYNC_MINUTES
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.environ.get("ZOAIRK_LOG_DIR", os.path.join(ROOT, "logs"))
BRANCH = os.environ.get("ZOAIRK_LOG_BRANCH", "play-logs")
WORKTREE = os.path.join(ROOT, ".play-logs-worktree")
REMOTE = os.environ.get("ZOAIRK_LOG_REMOTE", "origin")


def salt() -> str:
    path = os.path.join(LOG_DIR, ".salt")
    if not os.path.exists(path):
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(path, "w") as fh:
            fh.write(secrets.token_hex(16))
    return open(path).read().strip()


def anon_id(name: str, key: str) -> str:
    return "player-" + hashlib.sha256((key + name.strip().lower()).encode()).hexdigest()[:6]


def anonymize(records: list[dict], key: str) -> list[dict]:
    """Replace every player name, wherever it appears, with its anonymous ID."""
    names = sorted({r["player"] for r in records if r.get("player")}, key=len, reverse=True)
    if not names:
        return records
    ids = {n.lower(): anon_id(n, key) for n in names}
    pattern = re.compile(r"\b(" + "|".join(re.escape(n) for n in names) + r")\b", re.I)

    def scrub(value):
        if isinstance(value, str):
            return pattern.sub(lambda m: ids[m.group(0).lower()], value)
        if isinstance(value, list):
            return [scrub(v) for v in value]
        if isinstance(value, dict):
            return {k: scrub(v) for k, v in value.items()}
        return value

    return [scrub(r) for r in records]


def git(*args, cwd=None, check=True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd or ROOT, check=check, capture_output=True, text=True)


def ensure_worktree() -> None:
    if os.path.isdir(os.path.join(WORKTREE, ".git")) or os.path.isfile(os.path.join(WORKTREE, ".git")):
        return
    git("fetch", REMOTE, BRANCH, check=False)
    if git("rev-parse", "--verify", "--quiet", f"{REMOTE}/{BRANCH}", check=False).returncode == 0:
        git("worktree", "add", "-B", BRANCH, WORKTREE, f"{REMOTE}/{BRANCH}")
    else:                                            # first sync: an empty branch with only logs on it
        git("worktree", "add", "--detach", WORKTREE)
        git("checkout", "--orphan", BRANCH, cwd=WORKTREE)
        git("rm", "-rf", "--quiet", ".", cwd=WORKTREE, check=False)


def sync() -> str:
    files = sorted(glob.glob(os.path.join(LOG_DIR, "*.jsonl")))
    if not files:
        return "no logs yet"
    key = salt()
    ensure_worktree()
    git("pull", "--rebase", "--quiet", REMOTE, BRANCH, cwd=WORKTREE, check=False)
    out_dir = os.path.join(WORKTREE, "logs")
    os.makedirs(out_dir, exist_ok=True)
    for path in files:
        records = []
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        with open(os.path.join(out_dir, os.path.basename(path)), "w", encoding="utf-8") as fh:
            for r in anonymize(records, key):
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    git("add", "logs", cwd=WORKTREE)
    if git("diff", "--cached", "--quiet", cwd=WORKTREE, check=False).returncode == 0:
        return "no new log lines"
    git("commit", "--quiet", "-m", "Play logs (anonymized)", cwd=WORKTREE)
    push = git("push", "--quiet", REMOTE, f"HEAD:{BRANCH}", cwd=WORKTREE, check=False)
    if push.returncode != 0:
        return "committed locally; push failed: " + push.stderr.strip()[:200]
    return f"pushed {len(files)} log file(s) to {BRANCH}"


if __name__ == "__main__":
    try:
        print(sync())
    except subprocess.CalledProcessError as exc:
        print(f"sync failed: {exc.stderr.strip()[:300]}", file=sys.stderr)
        sys.exit(1)
