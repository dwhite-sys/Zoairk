"""Turn loop: player input → parse → state machine → narration → NPC gauge → save (contracts C1–C5)."""
from __future__ import annotations

import re

from .world import World

MOVE = re.compile(r"^\s*(?:go|walk|head|move|run)?\s*(north|south|east|west|up|down|n|s|e|w)\s*$", re.I)
SHORT = {"n": "north", "s": "south", "e": "east", "w": "west"}
LOOK = re.compile(r"^\s*(look|l|look around)\s*$", re.I)
SPEECH = re.compile(r"[\"“”]")


STATE_WORDS = {"open": "open", "on_fire": "on fire", "broken": "broken"}


def _msg(role: str, text: str, **extra) -> dict:
    return {"type": "message", "role": role, "text": text, **extra}


class Game:
    def __init__(self, world_path: str = "worlds/demo.json"):
        self.world = World(world_path)
        self.start = self.world.current.name
        self.locations: dict[str, str] = {}      # player -> scene name (each player moves on their own)

    def _enter(self, player: str) -> None:
        """Point the shared world at this player's own scene before handling their input."""
        self.world.current = self.world.scenes[self.locations.setdefault(player, self.start)]

    def describe(self) -> str:
        """Scene text plus every object whose state changed, so persistence is visible."""
        s = self.world.current
        notes = []
        for o in s.objects:
            on = [word for key, word in STATE_WORDS.items() if getattr(o.states, key, False)]
            if on:
                notes.append(f"The {o.properties.name} is {' and '.join(on)}.")
        return " ".join([s.description, *notes])

    def _scene(self) -> dict:
        s = self.world.current
        return {"type": "switch_scene", "scene": s.name, "description": self.describe()}

    def intro(self, player: str = "The player") -> list[dict]:
        self._enter(player)
        return [self._scene(), _msg("narrator", self.describe())]

    def handle(self, text: str, player: str = "The player") -> list[dict]:
        from . import interactions, narrator, npc, parser

        text = (text or "").strip()
        if not text:
            return []                                   # blank input: no turn, nothing changes
        self._enter(player)
        w = self.world
        if LOOK.match(text):
            return [_msg("narrator", self.describe())]
        m = MOVE.match(text)
        if m:
            direction = SHORT.get(m.group(1).lower(), m.group(1).lower())
            if not w.move(direction):
                return [_msg("system", "You can't go that way.")]
            self.locations[player] = w.current.name
            w.turn += 1
            w.save()
            return [{**self._scene(), "private": True}, _msg("narrator", self.describe(), private=True)]

        npcs = w.current.npcs
        if SPEECH.search(text):                          # quotes mark speech: no parse, straight to memory
            w.turn += 1
            event_text = f"{player} says: {text}"
            for n in npcs:
                n.remember(w.turn, "speech", event_text)
            spoken = " ".join(re.findall(r"[\"“]([^\"”]+)[\"”]", text)) or text
            said = spoken.strip().rstrip(",")
            out = [_msg("narrator", f'You say, "{said}"' if player == "The player" else f'{player} says, "{said}"')]
        else:
            actions = parser.parse(text, w)
            if not actions:                              # gibberish / nothing resolvable: no turn
                return [_msg("system", "Nothing happens.")]
            w.turn += 1
            events = interactions.run(actions)
            prose = narrator.narrate(events, w.current.description)
            event_text = f"{player}: {text}. Result: {prose}"
            for n in npcs:
                n.remember(w.turn, "action", event_text)
            out = [_msg("narrator", prose)]

        for d in npc.gauge(npcs, event_text, turn=w.turn):   # gauge records memory and the engage reply
            text = d.expression
            if d.decision == "express":                    # express is non-verbal: drop any quoted speech
                text = re.sub(r"\s*[\"“][^\"”]*[\"”]\s*", " ", text or "").strip()
            if d.decision in ("express", "engage") and text:
                out.append(_msg("npc", text, npc=d.npc, decision=d.decision,
                                confidence=round(d.confidence, 2)))
        w.save()
        return out
