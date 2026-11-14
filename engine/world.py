"""C5 world loading, lookup and persistence."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .objects import GameObject

ARTICLES = {"a", "an", "the", "my", "your", "his", "her", "its", "their", "some", "this", "that"}


@dataclass
class Npc:
    name: str
    profile: str
    memory: list[dict] = field(default_factory=list)

    def remember(self, turn: int, kind: str, text: str) -> None:
        self.memory.append({"turn": turn, "kind": kind, "text": text})


@dataclass
class Scene:
    name: str
    description: str
    exits: dict[str, str]
    objects: list[GameObject]
    npcs: list[Npc]


def _norm(name: str) -> str:
    words = [w for w in re.findall(r"[a-z0-9']+", (name or "").lower()) if w not in ARTICLES]
    return " ".join(words)


class World:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        doc = json.loads(self.path.read_text())
        self.name = doc["name"]
        self.aliases: dict[int, list[str]] = {}
        self.scenes: dict[str, Scene] = {}
        for sname, s in doc["scenes"].items():
            objs = []
            for o in s.get("objects", []):
                obj = GameObject(o["name"], templates=o.get("templates", []))
                obj.properties.description = o.get("description", "")
                if "text" in o:
                    obj.text = o["text"]
                self.aliases[id(obj)] = [_norm(o["name"])] + [_norm(a) for a in o.get("aliases", [])]
                objs.append(obj)
            npcs = [Npc(n["name"], n.get("profile", "")) for n in s.get("npcs", [])]
            self.scenes[sname] = Scene(sname, s.get("description", ""), s.get("exits", {}), objs, npcs)
        self.current = self.scenes[doc["start_scene"]]
        self.turn = 0

    def visible_objects(self) -> list[GameObject]:
        return [o for o in self.current.objects if getattr(o.states, "visible", True)]

    def find(self, name: str | None) -> GameObject | None:
        """Resolve a model-produced name to a visible object: exact alias, then word overlap."""
        if not name:
            return None
        n = _norm(name)
        objs = self.visible_objects()
        for o in objs:
            if n in self.aliases.get(id(o), []):
                return o
        words = set(n.split())
        best, score = None, 0
        for o in objs:
            for a in self.aliases.get(id(o), []):
                s = len(words & set(a.split()))
                if s > score:
                    best, score = o, s
        return best

    def move(self, direction: str) -> bool:
        target = self.current.exits.get(direction.lower())
        if target:
            self.current = self.scenes[target]
            return True
        return False

    def snapshot(self) -> dict:
        return {"world": self.name, "turn": self.turn, "scene": self.current.name,
                "objects": {f"{s.name}/{o.properties.name}": vars(o.states).copy()
                            for s in self.scenes.values() for o in s.objects},
                "npc_memory": {n.name: n.memory for s in self.scenes.values() for n in s.npcs}}

    def save(self, saves_dir: str | Path = "saves") -> Path:
        out = Path(saves_dir) / f"{self.path.stem}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(self.snapshot(), indent=1, default=str))
        return out
