"""Inventory rules through the state machine (no model calls)."""
from engine import inventory
from engine.game import Game


def test_take_weight_rules_containers_and_give():
    g = Game("worlds/demo.json"); g.intro("Drew"); g._enter("Drew")
    w, inv = g.world, g.inventories["Drew"]
    match, mailbox, leaflet = w.find("match"), w.find("mailbox"), w.find("leaflet")
    assert inventory.take(w, inv, match).ok and match in inv
    assert not inventory.take(w, inv, mailbox).ok                      # too heavy
    assert not inventory.put(w, inv, match, mailbox).ok                # mailbox closed
    mailbox.states.open = True
    assert inventory.take(w, inv, leaflet).ok and inventory.put(w, inv, leaflet, mailbox).ok
    assert leaflet in mailbox.contents and leaflet not in inv
    assert inventory.take(w, inv, leaflet, mailbox).message == "You take the leaflet from the mailbox."
    jerry = w.current.npcs[0]
    assert inventory.give(inv, match, jerry).ok and match in jerry.inventory
    assert g.status("Drew")["inventory"] == ["leaflet"]
    g.handle("go north", player="Drew")
    assert not inventory.take(w, inv, w.find("statue")).ok             # the statue rule


def test_dropped_item_shows_in_room_and_npc_uses_carried_weapon():
    g = Game("worlds/demo.json"); g.intro("Drew"); g._enter("Drew")
    w, inv = g.world, g.inventories["Drew"]
    inventory.take(w, inv, w.find("match"))
    g.handle("go north", player="Drew"); g._enter("Drew")
    inventory.drop(w, inv, w.find("match"))
    assert "a match" in g.describe().split("You also see:")[1]
    g._enter("Drew"); jerry = g.world.scenes["front_lawn"].npcs[0]
    g.locations["Drew"] = "front_lawn"; g._enter("Drew")
    ev = g._attack("Jerry", "Drew", "hammer", {}, ["Drew"], npc_weapon=True)
    assert ev.ok and ev.instrument == "hammer" and 3 <= 10 - g.player_hp["Drew"] <= 5
