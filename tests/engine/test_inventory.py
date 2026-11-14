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
