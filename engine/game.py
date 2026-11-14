"""Turn loop: player input → parse → state machine → narration → NPC gauge → save (contracts C1–C5)."""
from __future__ import annotations

import re

from . import combat, inventory
from .world import World

MOVE = re.compile(r"^\s*(?:go|walk|head|move|run)?\s*(north|south|east|west|up|down|n|s|e|w)\s*$", re.I)
SHORT = {"n": "north", "s": "south", "e": "east", "w": "west"}
LOOK = re.compile(r"^\s*(look|l|look around)\s*$", re.I)
INV = re.compile(r"^\s*(i|inv|inventory|what am i (carrying|holding))\??\s*$", re.I)
RESPAWN = re.compile(r"^\s*(respawn|revive|start over)\s*$", re.I)
HEALTH = re.compile(r"^\s*(health|hp|status|how am i)\??\s*$", re.I)
ITEM_VERBS = {"take", "drop", "put", "give", "loot"}
SPEECH = re.compile(r"[\"“”]")


STATE_WORDS = {"open": "open", "on_fire": "on fire", "broken": "broken", "ash": "burnt to ash"}
BURN_MIN_SECONDS = 60          # nothing burns out sooner than this
BURN_CHECK_SECONDS = 30        # then, every 30 s, each burning thing has a chance to burn out
BURN_CHANCE = 0.35             # => usually gone within about 1-2 minutes, slightly unpredictable
QUOTED = re.compile(r"[\"“][^\"”]*[\"”]")


EFFECTS = {"ignite": "fire", "extinguish": "extinguish", "break_object": "shatter", "throw": "throw",
           "attack": "hit", "open": "open", "close": "close", "read": "read"}


def _effects(events) -> list[str]:
    """Front-end cues for what actually happened (only successful events)."""
    return sorted({EFFECTS[e.action] for e in events if e.ok and e.action in EFFECTS}
                  | ({"shatter"} if any(e.ok and str(e.changed.get(k)) == "True" and k.endswith(".broken")
                                        for e in events for k in e.changed) else set()))


def _reveal_or_mask(npc, text: str) -> str:
    """An unknown NPC's name is revealed only when spoken aloud; otherwise narration uses its title."""
    if npc.known or not npc.title or not text:
        return text
    if any(npc.name in q for q in QUOTED.findall(text)):
        npc.known = True                       # introduced themselves: everyone here now knows
        return text
    title = npc.title
    text = re.sub(rf"(^|[.!?]\s+|\*)({re.escape(npc.name)})\b", lambda m: m.group(1) + title[0].upper() + title[1:], text)
    return re.sub(rf"\b{re.escape(npc.name)}\b", title, text)


def _msg(role: str, text: str, **extra) -> dict:
    return {"type": "message", "role": role, "text": text, **extra}


class Game:
    def __init__(self, world_path: str = "worlds/demo.json"):
        self.world = World(world_path)
        self.start = self.world.current.name
        self.locations: dict[str, str] = {}      # player -> scene name (each player moves on their own)
        self.player_hp: dict[str, int] = {}      # player -> health (combat)
        self.inventories: dict[str, list] = {}   # player -> carried GameObjects

    def _enter(self, player: str) -> None:
        """Point the shared world at this player's own scene (and inventory) before handling input."""
        self.world.current = self.world.scenes[self.locations.setdefault(player, self.start)]
        self.world.carried = self.inventories.setdefault(player, [])

    def tick(self, now: float) -> list[dict]:
        """World clock (runs on real time, independent of players): burning objects burn out to ash.
        Each message carries to_scene, so only players in that room see it. NPCs still act only on player time."""
        import random
        out = []
        for scene in self.world.scenes.values():
            for o in scene.objects + [c for x in scene.objects for c in getattr(x, "contents", [])]:
                st = o.states
                if not getattr(st, "on_fire", False) or getattr(st, "ash", False):
                    continue
                if not hasattr(o, "burn_until"):
                    o.burn_until = now + BURN_MIN_SECONDS        # first chance after the minimum
                    continue
                if now < o.burn_until:
                    continue
                if random.random() > BURN_CHANCE:                 # not this time; try again in 30 s
                    o.burn_until = now + BURN_CHECK_SECONDS
                    continue
                if "igniter" not in o.attributes:
                    st.on_fire, st.ash = False, True
                    out.append(_msg("narrator", f"The {o.properties.name} burns down to a pile of ash.",
                                    to_scene=scene.name, effects=["ash"]))
                else:                                     # a match just burns out
                    st.on_fire = False
                    del o.burn_until
                    out.append(_msg("narrator", f"The {o.properties.name} burns out.", to_scene=scene.name,
                                    effects=["extinguish"]))
        if out:
            self.world.save()
        return out

    def status(self, player: str) -> dict:
        """Private per-player status for the front end: health and inventory."""
        return {"type": "status", "player": player, "private": True, "hp": self.player_hp.get(player, 10),
                "max": combat.MAX_HP, "inventory": [o.properties.name for o in self.inventories.get(player, [])]}

    def _items(self, player, c, npcs) -> "Event":
        """take / drop / put / give, resolved by the inventory rules."""
        from .types import Event
        w, inv = self.world, self.inventories[player]
        obj, other = w.find(c.get("target")), (c.get("instrument") or "").strip()
        if c["key"] == "loot":
            obj = True
        if obj is None:
            return Event(c["key"], False, c.get("target"), None, {}, f"You don't see any {c.get('target')} here.")
        key = c["key"]
        if key == "loot":
            return self._loot(player, c.get("target") or "", npcs)
        if key == "take":
            src = w.find(other) if other else None
            return inventory.take(w, inv, obj, src if src is not obj else None)
        if key == "drop":
            return inventory.drop(w, inv, obj)
        if key == "put":
            return inventory.put(w, inv, obj, w.find(other))
        npc = next((n for n in npcs if other.lower() in (n.name.lower(), (n.title or "").lower(),
                                                         (n.title or "").lower().removeprefix("the "))), None)
        if npc is None:
            return Event("give", False, obj.properties.name, other, {}, f"There is no {other or 'one'} here to give it to.")
        return inventory.give(inv, obj, npc)

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
                notes.append(f"{n.label} is {combat.status(n.hp)}.")
        loose = [o.properties.name for o in s.objects
                 if o.properties.name.lower() not in s.description.lower()]
        if loose:
            notes.append("You also see: " + ", ".join(f"a {x}" for x in loose) + ".")
        return " ".join([s.description, *notes])

    def _scene(self) -> dict:
        s = self.world.current
        return {"type": "switch_scene", "scene": s.name, "description": self.describe()}

    def _attack(self, attacker, target, weapon, npcs_by_lower, players_here, npc_weapon=False):
        """Resolve one attack through the state machine (combat.strike) and return an Event."""
        from .types import Event
        hp = {**{n.name: n.hp for n in npcs_by_lower.values()}, **{p: self.player_hp.get(p, 10) for p in players_here}}
        t = (target or "").strip().lower()
        if t in npcs_by_lower:                       # name or title ("the guard") of an NPC
            t = npcs_by_lower[t].name.lower()
        name = next((k for k in hp if k.lower() == t), None)
        if name is None:
            return Event("attack", False, target, weapon, {}, f"{target} is not here.")
        if weapon and not npc_weapon and self.world.find(weapon) is None:   # players need it in hand/room
            weapon = None
        wobj = None
        if weapon:
            wobj = self.world.find(weapon) if not npc_weapon else next(
                (i for n in self.world.current.npcs for i in n.inventory if i.properties.name == weapon), None)
        r = combat.strike(attacker, name, hp, weapon, getattr(wobj, "damage", None))
        if not r["ok"]:
            return Event("attack", False, name, weapon, {}, r["message"])
        by_name = {n.name.lower(): n for n in npcs_by_lower.values()}
        if name.lower() in by_name:
            by_name[name.lower()].hp = r["hp"]
            r["message"] = r["message"].replace(name, by_name[name.lower()].label)
        else:
            self.player_hp[name] = r["hp"]
            if r["hp"] <= 0:                          # death: belongings drop where the player fell
                dropped = self.inventories.get(name, [])
                where = self.world.scenes[self.locations.get(name, self.start)]
                where.objects.extend(dropped)
                if dropped:
                    r["message"] += f" {name}'s belongings fall to the ground: " + ", ".join(o.properties.name for o in dropped) + "."
                self.inventories[name] = []
        return Event("attack", True, name, weapon, {f"{name}.hp": r["hp"], f"{name}.status": r["status"]}, r["message"])

    def _loot(self, player, target, npcs):
        """Take everything a dead NPC carried."""
        from .types import Event
        t = re.sub(r"('s)?\s*(dead\s+)?(body|corpse)$", "", target.strip(), flags=re.I).strip().lower()
        n = next((x for x in npcs if t in (x.name.lower(), (x.title or "").lower(),
                                            (x.title or "").lower().removeprefix("the "))), None)
        if n is None:
            return Event("loot", False, target, None, {}, f"There is no {target} here to loot.")
        if n.hp > 0:
            return Event("loot", False, n.label, None, {}, f"{n.label} is very much alive and won't let you.")
        if not n.inventory:
            return Event("loot", True, n.label, None, {}, f"You search {n.label}'s body but find nothing.")
        got = [o.properties.name for o in n.inventory]
        self.inventories[player].extend(n.inventory)
        n.inventory = []
        return Event("loot", True, n.label, None, {f"{n.name}.looted": True},
                     f"You search {n.label}'s body and take: {', '.join(got)}.")

    def intro(self, player: str = "The player") -> list[dict]:
        self._enter(player)
        return [self._scene(), _msg("scene", self.describe())]

    def handle(self, text: str, player: str = "The player") -> list[dict]:
        from . import interactions, narrator, npc, parser

        text = (text or "").strip()
        if not text:
            return []                                   # blank input: no turn, nothing changes
        self._enter(player)
        w = self.world
        if LOOK.match(text):
            return [_msg("scene", self.describe())]
        if INV.match(text):
            items = [o.properties.name for o in self.inventories[player]]
            return [_msg("system", "You are carrying: " + (", ".join(items) or "nothing") + ".", private=True),
                    self.status(player)]
        if HEALTH.match(text):
            hp = self.player_hp.get(player, 10)
            return [_msg("system", f"Health: {hp}/{combat.MAX_HP} ({combat.status(hp)}).", private=True),
                    self.status(player)]
        if RESPAWN.match(text):
            if self.player_hp.get(player, 10) > 0:
                return [_msg("system", "You're still alive.", private=True)]
            left = w.current.name
            self.player_hp[player] = combat.MAX_HP
            self.locations[player] = self.start
            self._enter(player)
            for n in w.current.npcs:              # NPCs keep their memories: they saw you die
                n.remember(w.turn, "action", f"{player}, who was killed here earlier and lay dead, has impossibly "
                                             f"come back to life and is standing here again.")
            w.save()
            return [{**self._scene(), "private": True},
                    _msg("system", "You wake up with a gasp, whole again.", private=True),
                    _msg("scene", self.describe(), private=True),
                    _msg("system", f"{player} comes back to life.", to_scene=self.start, others_only=True),
                    self.status(player)]
        if self.player_hp.get(player, 10) <= 0:
            return [_msg("system", "You are dead. You can only look around, or respawn.", private=True)]
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
            return [{**self._scene(), "private": True}, _msg("scene", self.describe(), private=True),
                    _msg("system", f"{player} heads {direction}.", to_scene=left, others_only=True),
                    _msg("system", f"{player} arrives.", to_scene=arrived, others_only=True), self.status(player)]

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
            for n in npcs:                               # "attack the guard" works before you know his name
                if n.hp > 0 and n.title:
                    alive_npcs[n.title.lower()] = n
                    alive_npcs[n.title.lower().removeprefix("the ")] = n
            w.people_here = [n.label for n in npcs if n.hp > 0] + here
            calls = parser.extract_calls(text, w)
            fights, rest, items = [], [], []
            for c in calls:
                if c.get("key") in ITEM_VERBS:
                    items.append(c)
                    continue
                tgt = (c.get("target") or "").strip()
                if c.get("key") == "attack" and (tgt.lower() in alive_npcs or tgt in here or tgt.lower() in [h.lower() for h in here]):
                    fights.append(c)
                else:
                    rest.append(c)
            actions = parser.calls_to_action_sets(rest, w)
            if not actions and not fights and not items:   # gibberish / nothing resolvable: no turn
                return [_msg("system", "Nothing happens.")]
            w.turn += 1
            events = [self._items(player, c, npcs) for c in items] + interactions.run(actions)
            for c in fights:
                events.append(self._attack(player, c["target"], c.get("instrument") or None, alive_npcs, here))
            for e in events:                       # opening a container reveals what is inside (Zork)
                if e.action == "open" and e.ok:
                    box = w.find(e.target)
                    if box is not None and hasattr(box, "contents"):
                        inside = ", ".join(f"a {o.properties.name}" for o in box.contents) or "nothing"
                        e.message += f" Inside the {e.target}: {inside}."
            if re.search(r"\b(throw|threw|hurl|toss|chuck|lob|fling)\b", text, re.I):
                inv = self.inventories[player]
                for c in fights + rest:               # whatever was thrown lands in the room
                    for nm in (c.get("instrument"), c.get("target")):
                        o = w.find(nm) if nm else None
                        if o is not None and o in inv:
                            inv.remove(o)
                            w.current.objects.append(o)
                            events.append(Event("drop", True, o.properties.name, None, {}, f"The {o.properties.name} lands on the ground."))
            prose = narrator.narrate(events, w.current.description)
            event_text = f"{player}: {text}. Result: {prose}"
            for n in npcs:
                n.remember(w.turn, "action", event_text)
            hit = next((e.target for e in events if e.action == "attack" and e.ok), None)
            out = [_msg("narrator", prose, effects=_effects(events), **({"hit": hit} if hit else {}))]

        focus = next((n.name for n in npcs if re.search(rf"\b{re.escape(n.name)}\b", text, re.I)
                      or (n.title and n.title.lower().removeprefix("the ") in text.lower())), None)
        for d in npc.gauge(npcs, event_text, turn=w.turn, focus=focus):   # gauge records memory and the engage reply
            who = next(n for n in npcs if n.name == d.npc)
            text = _reveal_or_mask(who, d.expression)
            if d.decision == "express":                    # express is non-verbal: drop any quoted speech
                text = re.sub(r"\s*[\"“][^\"”]*[\"”]\s*", " ", text or "").strip()
            if d.decision in ("express", "engage") and text:
                out.append(_msg("npc", text, npc=who.label, decision=d.decision,
                                confidence=round(d.confidence, 2)))
            if d.decision == "engage" and d.attack:
                present = {n.name.lower(): n for n in npcs if n.hp > 0 and n.name != d.npc}
                players_here = [p for p, loc in self.locations.items() if loc == w.current.name]
                weapon = next((i.properties.name for i in who.inventory if getattr(i.properties, "weight", 0) >= 1), None)
                ev = self._attack(d.npc, d.attack, weapon, present, players_here, npc_weapon=True)
                if ev.ok:
                    out.append(_msg("narrator", "⚔ " + ev.message, effects=["hit"], hit=ev.target))
                    killed = " and killed them" if "now dead" in ev.message else ""
                    for n in npcs:            # every NPC here remembers the fight, including who died
                        n.remember(w.turn, "action", f"{d.npc} attacked {ev.target}{killed}. {ev.message}")
        w.save()
        players_here = [p for p, loc in self.locations.items() if loc == w.current.name]
        return out + [self.status(p) for p in players_here]
