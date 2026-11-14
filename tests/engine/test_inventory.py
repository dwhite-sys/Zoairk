"""Inventory rules through the state machine (no model calls)."""
from engine import inventory
from engine.game import Game


def test_take_weight_rules_containers_and_give():
    g = Game("worlds/demo.json"); g.intro("Drew"); g._enter("Drew")
    w, inv = g.world, g.inventories["Drew"]
    match, mailbox = w.find("match"), w.find("mailbox")
    assert w.find("leaflet") is None                                     # hidden in the closed mailbox
    mailbox.states.open = True
    leaflet = w.find("leaflet")
    assert inventory.take(w, inv, leaflet, mailbox).ok and leaflet in inv     # take from the open mailbox
    mailbox.states.open = False
    assert inventory.take(w, inv, match).ok and match in inv
    assert not inventory.take(w, inv, mailbox).ok                      # too heavy
    assert not inventory.put(w, inv, match, mailbox).ok                # mailbox closed
    mailbox.states.open = True
    assert inventory.put(w, inv, leaflet, mailbox).ok
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
    assert "a match lie on the ground nearby" in g.describe() or "match" in g.describe().split(".")[-2]
    g._enter("Drew"); jerry = g.world.scenes["front_lawn"].npcs[0]
    g.locations["Drew"] = "front_lawn"; g._enter("Drew")
    ev = g._attack("Jerry", "Drew", "hammer", {}, ["Drew"], npc_weapon=True)
    assert ev.ok and ev.instrument == "hammer" and 3 <= 10 - g.player_hp["Drew"] <= 5


def test_health_potion_heals_and_is_used_up():
    from engine import combat
    g = Game("worlds/demo.json"); g.intro("Drew"); g._enter("Drew")
    joe = g.world.current.npcs[1]
    potion = next(i for i in joe.inventory if i.properties.name == "health potion")
    joe.inventory.remove(potion); g.inventories["Drew"].append(potion)
    g.player_hp["Drew"] = 4
    ev = g._items("Drew", {"key": "drink", "target": "health potion", "instrument": ""}, g.world.current.npcs)
    assert ev.ok and g.player_hp["Drew"] == 9 and potion not in g.inventories["Drew"]
