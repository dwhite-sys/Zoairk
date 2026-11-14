"""Shared engine types. ActionSet/ObjectEntry come from dwhite-sys/nlp_state_machine (ailess_srl.py)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .objects import GameObject


@dataclass
class ObjectEntry:
    object: GameObject
    word: str
    place: int = 0


@dataclass
class ActionSet:
    target: ObjectEntry | None
    action: str
    instrument: ObjectEntry | None = None
    indicator: str | None = None
    locational_indicator: str | None = None


@dataclass
class Event:
    """C2: what a handler returns instead of printing. The narrator turns it into prose."""
    action: str
    ok: bool
    target: str | None = None
    instrument: str | None = None
    changed: dict[str, Any] = field(default_factory=dict)
    message: str = ""


@dataclass
class NpcDecision:
    """C3: one NPC's choice for the latest event."""
    npc: str
    decision: str            # "nothing" | "express" | "engage"
    confidence: float
    expression: str = ""
    attack: str = ""          # engage only: someone present the NPC attacks
    give: str = ""            # engage only: an item the NPC hands to the player who acted
