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
        "give": {"type": "string", "description": "Only with engage: the exact name of an item YOU carry that you hand to the player who just acted (e.g. because they paid, asked nicely, or threatened you), or empty."},
        "attack": {"type": "string", "description": "Only with engage: the exact name of someone present this NPC physically attacks, or empty. Only for real provocation (being attacked, threatened, or deeply wronged)."},
        "confidence": {"type": "number"},
        "expression": {"type": "string"}}, "required": ["decision", "confidence"]}}}]
DECIDE_SYS = ("Call npc_decide exactly once. You decide how one NPC in a text adventure responds to the latest event. "
              "Choose: nothing (NPC not involved or it is not relevant to them), express (a short non-verbal reaction, body language only, NO spoken words or quotes, and NO attacks or physical contact with anyone; "
              "give it as 'expression' in third person), engage (the NPC speaks or acts). "
              "confidence is 0-1: how strongly this NPC wants to respond. "
              "If the NPC hands over an item it carries in this response (because the player asked for it, paid, "
              "or threatened them and the NPC gives in), you MUST set give to that item's exact name; an item is "
              "only handed over if give is set.")
ENGAGE_SYS = ("You are playing an NPC in a text adventure. Stay in character. Reply with 1-3 sentences: what the NPC "
              "says (in quotes) and/or does. No narration of the player's actions, no meta commentary.")


def _memory(npc: Npc, n: int = 8) -> str:
    return "\n".join(f"- turn {m['turn']} {m['kind']}: {m['text']}" for m in npc.memory[-n:]) or "(none)"


def _remember(npc: Npc, kind: str, text: str, turn: int) -> None:
    npc.remember(turn, kind, text)


def _carrying(npc: Npc) -> str:
    items = [o.properties.name for o in getattr(npc, "inventory", [])]
    return f"You are carrying: {', '.join(items)}.\n" if items else ""


def _secrecy(npc: Npc) -> str:
    """Strangers do not know this NPC's name: never leak it in narration."""
    if getattr(npc, "known", True):
        return ""
    return (f"The players do NOT know your name. In the expression text refer to yourself only as "
            f"'{npc.title}', never as {npc.name}. You may reveal your name only by saying it aloud.\n")


def _decide_raw(npc: Npc, event_text: str) -> NpcDecision:
    msg = chat([{"role": "system", "content": DECIDE_SYS},
                {"role": "user", "content": f"NPC: {npc.profile}\n{_carrying(npc)}{_secrecy(npc)}Recent memory:\n{_memory(npc)}\nEvent: {event_text}"}],
               tools=TOOL, temperature=0)
    try:
        args = msg["tool_calls"][0]["function"]["arguments"]
        decision = args.get("decision")
        if decision not in LABELS:
            raise ValueError(decision)
        conf = max(0.0, min(1.0, float(args.get("confidence", 0.0))))
        attack = str(args.get("attack") or "").strip() if decision == "engage" else ""
        give = str(args.get("give") or "").strip() if decision == "engage" else ""
        return NpcDecision(npc.name, decision, conf, str(args.get("expression") or ""), attack, give)
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


NOISE_SIGMA = 0.15   # how chaotic NPC choices feel
ENGAGE_FLOOR = 0.5   # a noisy engage score below this becomes an express


def gauge(npcs: list[Npc], event_text: str, turn: int = 0, focus: str | None = None) -> list[NpcDecision]:
    """Decide for all NPCs concurrently; at most one engages, chosen by confidence plus noise."""
    npcs = [n for n in npcs if getattr(n, "hp", 1) > 0]          # the dead do not act
    if not npcs:
        return []
    with ThreadPoolExecutor(max_workers=3) as ex:
        decisions = list(ex.map(lambda n: _decide_raw(n, event_text), npcs))
    # Bias plus noise (decided with Drew 13:20): the model's confidence is the bias, and Gaussian noise
    # adds "a little random chance for pizzazz". The best noisy engage wins; an engage whose noisy score
    # falls under ENGAGE_FLOOR, or that loses to a stronger one, becomes an express instead.
    noisy = {id(d): d.confidence + random.gauss(0.0, NOISE_SIGMA) for d in decisions}
    for d in decisions:          # the NPC the player attacked or spoke to is directly involved: it always gets its say
        if focus and d.npc.lower() == focus.lower() and d.decision == "engage":
            noisy[id(d)] = 10.0
    ranked = sorted(decisions, key=lambda d: noisy[id(d)], reverse=True)
    engages = [d for d in ranked if d.decision == "engage"]
    for i, d in enumerate(engages):
        if i > 0 or noisy[id(d)] < ENGAGE_FLOOR:
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
                {"role": "user", "content": f"You are: {npc.profile}\n{_carrying(npc)}{_secrecy(npc)}Your recent memory:\n{_memory(npc)}\n"
                                            f"What just happened: {event_text}\nYour response:"}],
               temperature=0.7)
    reply = (msg.get("content") or "").strip() or f"{npc.label} glares in silence."
    if turn is not None:
        _remember(npc, "engagement", reply, turn)
    return reply
