"""Asynchronous world events and cross-room permanence (no model calls)."""
from engine import interactions, inventory
from engine.game import Game
from engine.types import ActionSet, ObjectEntry


def test_burning_object_turns_to_ash_on_the_clock():
    g = Game("worlds/demo.json"); g._enter("Dawson")
    m, box = g.world.find("match"), g.world.find("mailbox")
    interactions.run([ActionSet(ObjectEntry(m, "match"), "ignite"),
                      ActionSet(ObjectEntry(box, "mailbox"), "ignite", ObjectEntry(m, "match"))])
    import random
    random.seed(0)
    assert g.tick(0.0) == []                       # timers start
    assert g.tick(30.0) == []                      # never before the 60 s minimum
    out = []
    for t in range(60, 2000, 30):                  # every 30 s a chance; eventually it burns out
        out += g.tick(float(t))
    texts = {x["text"] for x in out}
    assert "The mailbox burns down to a pile of ash." in texts and box.states.ash and not box.states.on_fire
    assert all(x["to_scene"] == "front_lawn" for x in out)
    assert "burnt to ash" in g.describe()


def test_dropped_item_persists_across_rooms():
    g = Game("worlds/demo.json"); g.intro("Drew"); g._enter("Drew")
    w, inv = g.world, g.inventories["Drew"]
    rock = w.find("rock"); inventory.take(w, inv, rock)
    g.handle("go north", player="Drew"); g._enter("Drew")
    assert inventory.drop(w, inv, rock).ok
    g.handle("go south", player="Drew"); g.handle("go north", player="Drew"); g._enter("Drew")
    assert w.find("rock") is rock and rock in w.current.objects
