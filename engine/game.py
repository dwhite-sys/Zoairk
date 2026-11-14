"""Turn loop: player input → parse → state machine → narration → NPC gauge → save (contracts C1–C5)."""
from __future__ import annotations

import re

from . import combat
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
        self.player_hp: dict[str, int] = {}      # player -> health (combat)

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
        for n in s.npcs:
            if n.hp < 10:
                notes.append(f"{n.name} is {combat.status(n.hp)}.")
        return " ".join([s.description, *notes])

    def _scene(self) -> dict:
        s = self.world.current
        return {"type": "switch_scene", "scene": s.name, "description": self.describe()}

    def _attack(self, attacker, target, weapon, npcs_by_lower, players_here):
        """Resolve one attack through the state machine (combat.strike) and return an Event."""
        from .types import Event
        hp = {**{n.name: n.hp for n in npcs_by_lower.values()}, **{p: self.player_hp.get(p, 10) for p in players_here}}
        name = next((k for k in hp if k.lower() == (target or "").strip().lower()), None)
        if name is None:
            return Event("attack", False, target, weapon, {}, f"{target} is not here.")
        if weapon and self.world.find(weapon) is None:
            weapon = None
        r = combat.strike(attacker, name, hp, weapon)
        if not r["ok"]:
            return Event("attack", False, name, weapon, {}, r["message"])
        if name.lower() in npcs_by_lower:
            npcs_by_lower[name.lower()].hp = r["hp"]
        else:
            self.player_hp[name] = r["hp"]
        return Event("attack", True, name, weapon, {f"{name}.hp": r["hp"], f"{name}.status": r["status"]}, r["message"])

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
        if self.player_hp.get(player, 10) <= 0:
            return [_msg("system", "You are dead. You can only look around.")]
        m = MOVE.match(text)
        if m:
            direction = SHORT.get(m.group(1).lower(), m.group(1).lower())
            left = w.current.name
            if not w.move(direction):
                return [_msg("system", "You can't go that way.")]
            self.locations[player] = w.current.name
            w.turn += 1
            w.save()
            arrived = w.current.name
            return [{**self._scene(), "private": True}, _msg("narrator", self.describe(), private=True),
                    _msg("system", f"{player} heads {direction}.", to_scene=left, others_only=True),
                    _msg("system", f"{player} arrives.", to_scene=arrived, others_only=True)]

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
            here = [p for p, loc in self.locations.items() if loc == w.current.name and p != player]
            alive_npcs = {n.name.lower(): n for n in npcs if n.hp > 0}
            w.people_here = [n.name for n in alive_npcs.values()] + here
            calls = parser.extract_calls(text, w)
            fights, rest = [], []
            for c in calls:
                tgt = (c.get("target") or "").strip()
                if c.get("key") == "attack" and (tgt.lower() in alive_npcs or tgt in here or tgt.lower() in [h.lower() for h in here]):
                    fights.append(c)
                else:
                    rest.append(c)
            actions = parser.calls_to_action_sets(rest, w)
            if not actions and not fights:              # gibberish / nothing resolvable: no turn
                return [_msg("system", "Nothing happens.")]
            w.turn += 1
            events = interactions.run(actions)
            for c in fights:
                events.append(self._attack(player, c["target"], c.get("instrument") or None, alive_npcs, here))
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
            if d.decision == "engage" and d.attack:
                present = {n.name.lower(): n for n in npcs if n.hp > 0 and n.name != d.npc}
                players_here = [p for p, loc in self.locations.items() if loc == w.current.name]
                ev = self._attack(d.npc, d.attack, None, present, players_here)
                if ev.ok:
                    out.append(_msg("narrator", "⚔ " + ev.message))
        w.save()
        return out
