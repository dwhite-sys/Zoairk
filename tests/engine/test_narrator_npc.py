"""Live-model gate for narrator + NPC gauge (needs Ollama with deepseek-v4.1-flash:cloud)."""
import time
from pathlib import Path

from engine.narrator import narrate
from engine.npc import LABELS, engage, gauge
from engine.types import Event
from engine.world import World

DEMO = Path(__file__).resolve().parents[2] / "worlds" / "demo.json"


def _npcs():
    w = World(DEMO)
    return w, {n.name: n for n in w.current.npcs}


def test_narrate_mentions_mailbox():
    w, _ = _npcs()
    t = time.time()
    out = narrate([Event("ignite", True, "mailbox", "match", {"mailbox.on_fire": True}, "mailbox is now on fire")],
                  w.current.description)
    print(f"narrate {time.time() - t:.1f}s: {out}")
    assert out and "mailbox" in out.lower()


def test_narrate_no_events():
    assert narrate([], "x")


def test_gauge_jerry_joe():
    _, npcs = _npcs()
    t = time.time()
    ds = gauge([npcs["Jerry"], npcs["Joe"]], "Player sets the mailbox on fire right next to Jerry")
    print(f"gauge {time.time() - t:.1f}s: {ds}")
    assert len(ds) == 2
    assert all(d.decision in LABELS for d in ds)
    assert sum(d.decision == "engage" for d in ds) <= 1
    assert npcs["Jerry"].memory and npcs["Joe"].memory


def test_engage_jerry():
    _, npcs = _npcs()
    t = time.time()
    out = engage(npcs["Jerry"], 'Player says to Jerry: "You suck."')
    print(f"engage {time.time() - t:.1f}s: {out}")
    assert out.strip()
    assert npcs["Jerry"].memory[-1]["kind"] == "engagement"
