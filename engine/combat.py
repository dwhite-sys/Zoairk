"""Combat: players and NPCs attack each other. The state machine owns health; models only choose targets.

Health 10. Damage 1-3 bare-handed, 3-5 with a weapon. State: alive (10), injured (1-9), dead (0).
State persists (board B3: "state of NPCs (dead/alive/injured) must persist").
"""
from __future__ import annotations

import random

MAX_HP = 10


def status(hp: int) -> str:
    return "dead" if hp <= 0 else ("injured" if hp < MAX_HP else "alive")


def strike(attacker: str, target: str, hp: dict[str, int], weapon: str | None = None,
           damage: tuple[int, int] | None = None) -> dict:
    """Apply one attack to `hp[target]`; returns an event dict for narration."""
    if hp.get(target, MAX_HP) <= 0:
        return {"ok": False, "message": f"{target} is already dead."}
    lo, hi = damage or ((3, 5) if weapon else (1, 3))     # a weapon's own range, else generic
    dmg = random.randint(lo, hi)
    hp[target] = max(0, hp.get(target, MAX_HP) - dmg)
    with_w = f" with the {weapon}" if weapon else ""
    return {"ok": True, "attacker": attacker, "target": target, "damage": dmg, "hp": hp[target],
            "status": status(hp[target]),
            "message": f"{attacker} attacks {target}{with_w} for {dmg} damage; {target} is now "
                       f"{status(hp[target])} ({hp[target]}/{MAX_HP})."}
