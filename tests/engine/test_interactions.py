from pathlib import Path

import pytest

from engine.interactions import INTERACTIONS, run
from engine.types import ActionSet, ObjectEntry
from engine.world import World

DEMO = Path(__file__).resolve().parents[2] / "worlds" / "demo.json"


@pytest.fixture
def world():
    w = World(DEMO)
    w.find("mailbox").states.open = True     # the leaflet lives inside the mailbox (Zork)
    return w


def AS(world, action, target, instrument=None):
    e = lambda n: ObjectEntry(world.find(n), n) if n else None
    return ActionSet(target=e(target), action=action, instrument=e(instrument))


def test_keys():
    assert set(INTERACTIONS) == {"ignite", "extinguish", "open", "close", "read", "break_object", "throw", "examine"}


def test_open_mailbox(world):
    world.find("mailbox").states.open = False
    (ev,) = run([AS(world, "open", "mailbox")])
    assert ev.ok and ev.changed == {"mailbox.open": True} and ev.target == "mailbox"
    assert world.find("mailbox").states.open is True


def test_ignite_chain(world):
    e1, e2 = run([AS(world, "ignite", "match"), AS(world, "ignite", "mailbox", "match")])
    assert e1.ok and e1.changed == {"match.on_fire": True}
    assert e2.ok and e2.changed == {"mailbox.on_fire": True} and e2.instrument == "match"


def test_ignite_with_unlit_match_fails(world):
    (ev,) = run([AS(world, "ignite", "mailbox", "match")])
    assert not ev.ok and ev.changed == {}
    assert world.find("mailbox").states.on_fire is False


def test_read_leaflet(world):
    (ev,) = run([AS(world, "read", "leaflet")])
    assert ev.ok and "WELCOME" in ev.message and ev.changed == {}


@pytest.mark.parametrize("target,instrument", [("rock", "window"), ("window", "rock")])
def test_throw_rock_at_window(world, target, instrument):
    (ev,) = run([AS(world, "throw", target, instrument)])
    assert ev.ok and ev.changed == {"window.broken": True}


def test_break_window(world):
    (ev,) = run([AS(world, "break_object", "window")])
    assert ev.ok and ev.changed == {"window.broken": True}


def test_ignite_rock_fails(world):
    before = vars(world.find("rock").states).copy()
    (ev,) = run([AS(world, "ignite", "rock")])
    assert not ev.ok and ev.changed == {}
    assert vars(world.find("rock").states) == before


def test_extinguish_and_close(world):
    evs = run([AS(world, "ignite", "match"), AS(world, "extinguish", "match"),
               AS(world, "open", "mailbox"), AS(world, "close", "mailbox"), AS(world, "examine", "rock")])
    assert [e.ok for e in evs] == [True] * 5
    assert evs[1].changed == {"match.on_fire": False} and evs[3].changed == {"mailbox.open": False}
    assert "rock" in evs[4].message


def test_unknown_action(world):
    (ev,) = run([AS(world, "dance", "rock")])
    assert not ev.ok and ev.message == "nothing happens"


def test_no_prints(world, capsys):
    run([AS(world, "examine", "mailbox"), AS(world, "read", "leaflet")])
    assert capsys.readouterr().out == ""
