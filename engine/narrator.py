"""C2 narrator: turns engine Events into short second-person prose."""
from __future__ import annotations

from .llm import chat
from .types import Event

SYS = ("You are the narrator of a text adventure. Write 1-3 vivid sentences in second person (\"you\"). "
       "Narrate ONLY what the events say happened. Never invent state changes, items, outcomes or NPC reactions (NPCs are narrated separately). "
       "If an event has ok=false, narrate that the attempt did not work. Plain prose, no lists, no quotes around it.")


def _fallback(events: list[Event]) -> str:
    return " ".join(e.message for e in events if e.message) or "Nothing happens."


def narrate(events: list[Event], scene_description: str) -> str:
    if not events:
        return "Nothing happens."
    lines = [f"- action={e.action} ok={e.ok} target={e.target} instrument={e.instrument} "
             f"changed={e.changed} message={e.message!r}" for e in events]
    msg = chat([{"role": "system", "content": SYS},
                {"role": "user", "content": f"Scene: {scene_description}\nEvents:\n" + "\n".join(lines)}],
               temperature=0.7)
    text = (msg.get("content") or "").strip()
    return text or _fallback(events)
