"""Summarise play logs: what players tried, what worked, and what didn't.

    python3 tools/log_report.py                 # all logs in logs/
    python3 tools/log_report.py logs/2026-11-14.jsonl --lobby play
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import statistics
from collections import Counter

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(paths, lobby=None):
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if lobby is None or r.get("lobby") == lobby:
                    yield r


def report(records) -> str:
    turns = [r for r in records if r.get("kind") == "turn"]
    if not turns:
        return "No turns logged yet."
    players = Counter(r.get("player") for r in turns)
    lobbies = Counter(r.get("lobby") for r in turns)
    nothing = [r for r in turns if r.get("nothing_happened")]
    errors = [r for r in turns if r.get("error")]
    secs = sorted(r.get("seconds") or 0 for r in turns)
    decisions = Counter(rep.get("decision") for r in turns for rep in r.get("replies", []) if rep.get("decision"))
    npcs = Counter(rep.get("npc") for r in turns for rep in r.get("replies", []) if rep.get("npc"))
    verbs = Counter((r.get("input") or "").strip().strip('"*').split(" ")[0].lower() for r in turns)
    lines = [
        f"Turns: {len(turns)}  players: {len(players)}  lobbies: {len(lobbies)}",
        f"Worked: {len(turns) - len(nothing) - len(errors)}  'Nothing happens': {len(nothing)} "
        f"({100 * len(nothing) / len(turns):.0f}%)  errors: {len(errors)}",
        f"Turn time: median {statistics.median(secs):.1f}s, p90 {secs[min(len(secs) - 1, round(0.9 * (len(secs) - 1)))]:.1f}s, max {secs[-1]:.1f}s",
        f"NPC responses: {dict(decisions)}  by NPC: {dict(npcs)}",
        f"Most-used first words: {', '.join(f'{w} ({n})' for w, n in verbs.most_common(10))}",
        f"Most active players: {', '.join(f'{p} ({n})' for p, n in players.most_common(5))}",
        "",
        "Did not work ('Nothing happens') - candidates for parser or world fixes:",
        *[f"  - [{r['lobby']}] {r.get('player')}: {r.get('input')}" for r in nothing[-25:]],
        "",
        "Errors:",
        *[f"  - [{r['lobby']}] {r.get('player')}: {r.get('input')} -> {r.get('error')}" for r in errors[-25:]],
        "",
        "Slowest turns:",
        *[f"  - {r.get('seconds')}s {r.get('player')}: {r.get('input')}"
          for r in sorted(turns, key=lambda r: -(r.get('seconds') or 0))[:5]],
    ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("files", nargs="*", help="log files (default: logs/*.jsonl)")
    ap.add_argument("--lobby", help="only this lobby")
    a = ap.parse_args()
    files = a.files or sorted(glob.glob(os.path.join(HERE, "logs", "*.jsonl")))
    print(report(list(load(files, a.lobby))))


if __name__ == "__main__":
    main()
