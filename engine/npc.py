"""C3 NPC gauge: decide (nothing/express/engage), gauge across NPCs, engage replies."""
from __future__ import annotations

import random
from concurrent.futures import ThreadPoolExecutor

from .llm import chat
from .types import NpcDecision
from .world import Npc

LABELS = ("nothing", "express", "engage")
TOOL = [{"type": "function", "function": {
    "name": "npc_decide", "description": "Record how this NPC responds to the latest event.",
    "parameters": {"type": "object", "properties": {
        "decision": {"type": "string", "enum": list(LABELS)},
        "confidence": {"type": "number"},
        "expression": {"type": "string"}}, "required": ["decision", "confidence"]}}}]
DECIDE_SYS = ("Call npc_decide exactly once. You decide how one NPC in a text adventure responds to the latest event. "
              "Choose: nothing (NPC not involved or it is not relevant to them), express (a short non-verbal reaction, body language only, NO spoken words or quotes; "
              "give it as 'expression' in third person), engage (the NPC speaks or acts). "
              "confidence is 0-1: how strongly this NPC wants to respond.")
ENGAGE_SYS = ("You are playing an NPC in a text adventure. Stay in character. Reply with 1-3 sentences: what the NPC "
              "says (in quotes) and/or does. No narration of the player's actions, no meta commentary.")


def _memory(npc: Npc, n: int = 8) -> str:
    return "\n".join(f"- turn {m['turn']} {m['kind']}: {m['text']}" for m in npc.memory[-n:]) or "(none)"


def _remember(npc: Npc, kind: str, text: str, turn: int) -> None:
    npc.remember(turn, kind, text)


def _decide_raw(npc: Npc, event_text: str) -> NpcDecision:
    msg = chat([{"role": "system", "content": DECIDE_SYS},
                {"role": "user", "content": f"NPC: {npc.profile}\nRecent memory:\n{_memory(npc)}\nEvent: {event_text}"}],
               tools=TOOL, temperature=0)
    try:
        args = msg["tool_calls"][0]["function"]["arguments"]
        decision = args.get("decision")
        if decision not in LABELS:
            raise ValueError(decision)
        conf = max(0.0, min(1.0, float(args.get("confidence", 0.0))))
        return NpcDecision(npc.name, decision, conf, str(args.get("expression") or ""))
    except Exception:
        return NpcDecision(npc.name, "nothing", 0.0)


def _record(npc: Npc, d: NpcDecision, turn: int, reply: str = "") -> None:
    if d.decision == "engage":
        _remember(npc, "engagement", reply or d.expression, turn)
    elif d.decision == "express":
        _remember(npc, "expression", d.expression, turn)
    else:
        _remember(npc, "inaction", "", turn)


def decide(npc: Npc, event_text: str, turn: int = 0) -> NpcDecision:
    d = _decide_raw(npc, event_text)
    _record(npc, d, turn)
    return d


def gauge(npcs: list[Npc], event_text: str, turn: int = 0) -> list[NpcDecision]:
    """Decide for all NPCs concurrently, then apply board B7b: one engage at most, chosen by coin flip."""
    with ThreadPoolExecutor(max_workers=3) as ex:
        decisions = list(ex.map(lambda n: _decide_raw(n, event_text), npcs))
    ranked = sorted(decisions, key=lambda d: d.confidence, reverse=True)
    engages = [d for d in ranked if d.decision == "engage"]
    if random.randint(0, 1) == 0:
        for d in engages[1:]:
            d.decision = "express"
    else:
        for d in engages:
            d.decision = "express"
    for d in ranked:
        if d.decision == "express" and not d.expression:
            d.expression = f"{d.npc} glances over."
    by_name = {n.name: n for n in npcs}
    for d in decisions:
        npc = by_name[d.npc]
        if d.decision == "engage":
            d.expression = engage(npc, event_text, turn=None)   # the reply travels with the decision
            _record(npc, d, turn, d.expression)
        else:
            _record(npc, d, turn)
    return decisions


def engage(npc: Npc, event_text: str, turn: int | None = 0) -> str:
    """The NPC's in-character reply. Records an engagement unless turn is None (gauge records it)."""
    msg = chat([{"role": "system", "content": ENGAGE_SYS},
                {"role": "user", "content": f"You are: {npc.profile}\nYour recent memory:\n{_memory(npc)}\n"
                                            f"What just happened: {event_text}\nYour response:"}],
               temperature=0.7)
    reply = (msg.get("content") or "").strip() or f"{npc.name} glares in silence."
    if turn is not None:
        _remember(npc, "engagement", reply, turn)
    return reply
