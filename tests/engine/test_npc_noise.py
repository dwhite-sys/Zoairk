"""Bias + noise selection (no model calls): confidence biases the choice, noise adds variety."""
import random

from engine import npc
from engine.types import NpcDecision
from engine.world import Npc


def _run(confidences, monkeypatch, seed):
    random.seed(seed)
    people = [Npc(f"N{i}", "") for i in range(len(confidences))]
    fixed = {p.name: NpcDecision(p.name, "engage", c, "glares") for p, c in zip(people, confidences)}
    monkeypatch.setattr(npc, "_decide_raw", lambda n, e: NpcDecision(**vars(fixed[n.name])))
    monkeypatch.setattr(npc, "engage", lambda n, e, turn=0, **kw: f"{n.name} speaks")
    return npc.gauge(people, "event")


def test_at_most_one_engage(monkeypatch):
    for seed in range(50):
        assert sum(d.decision == "engage" for d in _run([0.9, 0.85, 0.8], monkeypatch, seed)) <= 1


def test_confidence_biases_the_winner(monkeypatch):
    wins = sum(_run([0.95, 0.55], monkeypatch, s)[0].decision == "engage" for s in range(200))
    assert wins > 150          # the confident NPC usually engages, but not always (noise)


def test_low_confidence_engage_usually_becomes_express(monkeypatch):
    engaged = sum(_run([0.2], monkeypatch, s)[0].decision == "engage" for s in range(200))
    assert engaged < 10
