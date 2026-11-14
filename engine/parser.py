"""C1: player text -> ordered ActionSets via the tool-calling model (Ollama)."""
from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path

from .types import ActionSet, ObjectEntry
from .world import World

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
MODEL = "deepseek-v4.1-flash:cloud"
TIMEOUT = 30
TOOLS = [{"type": "function", "function": t}
         for t in json.loads((Path(__file__).resolve().parent.parent / "tools.json").read_text())]

SYSTEM = (
    "You parse a text-adventure player's ACTION into enter_command tool calls. "
    "Emit one call per action, in the order the actions HAPPEN in the world, not the order "
    "they are written (clauses introduced by before/after/once/then/first change the order). "
    "Use the object names given below for target and instrument. Give an instrument only if it "
    "is named or clearly implied (e.g. 'use it' refers to an earlier object); otherwise use an "
    "empty string. For 'put X in Y' and 'take X from Y', X is the target and Y the instrument; for "
    "'give X to someone', X is the target and the person is the instrument. If the input is speech in quotes, gibberish, or empty, call no tools."
)

# Verb normalisation to handler keys. Multi-word phrases are checked first.
VERB_MAP = {
    "set on fire": "ignite", "set fire to": "ignite", "set fire": "ignite", "put out": "extinguish",
    "look at": "examine", "light": "ignite", "ignite": "ignite", "burn": "ignite", "torch": "ignite",
    "strike": "ignite", "kindle": "ignite", "extinguish": "extinguish", "douse": "extinguish",
    "snuff": "extinguish", "blow out": "extinguish", "open": "open", "close": "close",
    "shut": "close", "read": "read", "smash": "break_object", "shatter": "break_object",
    "break": "break_object", "break_object": "break_object", "throw": "throw", "toss": "throw",
    "hurl": "throw", "examine": "examine", "inspect": "examine", "look": "examine",
    "attack": "attack", "hit": "attack", "punch": "attack", "kick": "attack", "stab": "attack",
    "fight": "attack", "slap": "attack", "shove": "attack", "tackle": "attack", "swing at": "attack",
    "pick up": "take", "take": "take", "grab": "take", "get": "take", "collect": "take",
    "drop": "drop", "put down": "drop", "discard": "drop",
    "put": "put", "place": "put", "stash": "put", "store": "put", "insert": "put",
    "give": "give", "hand": "give", "offer": "give",
}


def _is_speech_or_blank(text: str) -> bool:
    s = (text or "").strip()
    return not s or s[0] in "\"'“" or bool(re.search(r"[\"“][^\"”]+[\"”]", s))


def normalize_verb(verb: str) -> str | None:
    v = " ".join(re.findall(r"[a-z_]+", (verb or "").lower()))
    if v in VERB_MAP:
        return VERB_MAP[v]
    for phrase in sorted(VERB_MAP, key=len, reverse=True):
        if re.search(rf"\b{re.escape(phrase)}\b", v):
            return VERB_MAP[phrase]
    return None


def _call_model(text: str, world: World) -> list[dict]:
    names = ", ".join(o.properties.name for o in world.visible_objects())
    people = ", ".join(getattr(world, "people_here", []))
    if people:
        names += f". People here (valid targets for attack): {people}"
    body = {
        "model": MODEL, "stream": False, "think": False, "options": {"temperature": 0},
        "tools": TOOLS,
        "messages": [{"role": "system", "content": f"{SYSTEM}\nVisible objects: {names}."},
                     {"role": "user", "content": text}],
    }
    req = urllib.request.Request(OLLAMA_URL, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        msg = json.loads(r.read()).get("message", {})
    out = []
    for c in msg.get("tool_calls") or []:
        args = c.get("function", {}).get("arguments", {})
        if isinstance(args, str):
            args = json.loads(args)
        out.append(args)
    return out


def extract_calls(text: str, world: World) -> list[dict]:
    """Raw model calls with a normalised verb (`key`). [] on speech, blank input or any error."""
    if _is_speech_or_blank(text):
        return []
    try:
        calls = _call_model(text, world)
    except Exception:
        return []
    return [{"action": c.get("action", ""), "key": normalize_verb(c.get("action", "")),
             "target": c.get("target") or "", "instrument": c.get("instrument") or ""}
            for c in calls if isinstance(c, dict)]


def parse(text: str, world: World) -> list[ActionSet]:
    return calls_to_action_sets(extract_calls(text, world), world)


def calls_to_action_sets(calls: list[dict], world: World) -> list[ActionSet]:
    """Object interactions only; attacks on people are resolved by engine.combat."""
    sets = []
    for c in calls:
        target = world.find(c["target"])
        if c["key"] is None or target is None:
            continue
        inst = world.find(c["instrument"]) if c["instrument"] else None
        if inst is target:
            inst = None
        sets.append(ActionSet(target=ObjectEntry(target, c["target"]), action=c["key"],
                              instrument=ObjectEntry(inst, c["instrument"]) if inst else None))
    return sets
