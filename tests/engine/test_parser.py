"""C1 gate: parser against the live model and worlds/demo.json."""
from pathlib import Path

import pytest

from engine.parser import normalize_verb, parse
from engine.world import World

DEMO = Path(__file__).resolve().parents[2] / "worlds" / "demo.json"


@pytest.fixture
def world():
    return World(DEMO)


def _sig(sets):
    return [(s.action, s.target.object.properties.name,
             s.instrument.object.properties.name if s.instrument else None) for s in sets]


def test_normalize_verb():
    assert normalize_verb("set on fire") == "ignite"
    assert normalize_verb("put out") == "extinguish"
    assert normalize_verb("smash") == "break_object"
    assert normalize_verb("look at") == "examine"
    assert normalize_verb("pet") is None


def test_open_mailbox(world):
    assert _sig(parse("open the mailbox", world)) == [("open", "mailbox", None)]


def test_light_then_burn(world):
    got = _sig(parse("light the match and then use it to set the mailbox on fire", world))
    assert got == [("ignite", "match", None), ("ignite", "mailbox", "match")]


def test_before_clause(world):
    got = _sig(parse("before I open the box, I knock on it", world))
    assert ("open", "mailbox", None) in got


@pytest.mark.parametrize("text", ['say "hello" to Jerry', "asdkj qwpoe", "pet the unicorn", "", "   "])
def test_no_action(world, text):
    assert parse(text, world) == []
