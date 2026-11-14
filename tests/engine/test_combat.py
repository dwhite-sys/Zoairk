"""Combat goes through the state machine: health, injured/dead status, persistence (no model calls)."""
import random

from engine import combat
from engine.game import Game


def test_strike_damage_and_status():
    random.seed(1)
    hp = {"Jerry": 10}
    r = combat.strike("Drew", "Jerry", hp)
    assert r["ok"] and 1 <= r["damage"] <= 3 and hp["Jerry"] == 10 - r["damage"] and r["status"] == "injured"
    while hp["Jerry"] > 0:
        combat.strike("Drew", "Jerry", hp, weapon="rock")
    assert combat.status(hp["Jerry"]) == "dead"
    assert not combat.strike("Drew", "Jerry", hp)["ok"]


def test_player_vs_npc_and_player_vs_player_through_game():
    g = Game("worlds/demo.json"); g.intro("Dawson"); g.intro("Drew")
    npcs = {n.name.lower(): n for n in g.world.current.npcs}
    ev = g._attack("Dawson", "jerry", "rock", npcs, ["Drew"])
    assert ev.ok and npcs["jerry"].hp < 10 and "Jerry is injured." in g.describe()
    ev2 = g._attack("Dawson", "Drew", None, npcs, ["Drew"])
    assert ev2.ok and g.player_hp["Drew"] < 10
    g.player_hp["Drew"] = 0
    assert "dead" in g.handle("open the mailbox", player="Drew")[0]["text"]
    assert g.world.snapshot()["npc_hp"]["Jerry"] < 10          # persists in the save


def test_death_drops_belongings_and_respawn_keeps_npc_memory():
    from engine import inventory
    g = Game("worlds/demo.json"); g.intro("Drew"); g._enter("Drew")
    w = g.world
    inventory.take(w, g.inventories["Drew"], w.find("rock"))
    g.player_hp["Drew"] = 1
    npcs = {n.name.lower(): n for n in w.current.npcs}
    ev = g._attack("Jerry", "Drew", "hammer", npcs, ["Drew"], npc_weapon=True)
    assert g.player_hp["Drew"] == 0 and "belongings fall" in ev.message
    assert g.inventories["Drew"] == [] and w.find("rock") is not None          # dropped where he fell
    assert "respawn" in g.handle("open the mailbox", player="Drew")[0]["text"]
    out = g.handle("respawn", player="Drew")
    assert g.player_hp["Drew"] == 10 and any("wake up" in (m.get("text") or "") for m in out)
    assert any("come back to life" in e["text"] for e in w.current.npcs[0].memory)


def test_loot_dead_npc():
    g = Game("worlds/demo.json"); g.intro("Drew"); g._enter("Drew")
    jerry = g.world.current.npcs[0]
    npcs = g.world.current.npcs
    assert not g._loot("Drew", "Jerry", npcs).ok                    # alive: won't let you
    jerry.hp = 0
    ev = g._loot("Drew", "Jerry's body", npcs)
    assert ev.ok and "hammer" in ev.message and jerry.inventory == []
    assert [o.properties.name for o in g.inventories["Drew"]] == ["hammer"]


def test_weapon_damage_ranges_and_sword_in_chest():
    import random
    from engine import inventory
    g = Game("worlds/demo.json"); g.intro("Drew"); g.handle("go north", player="Drew"); g._enter("Drew")
    w = g.world
    chest = w.find("chest"); chest.states.open = True
    sword = w.find("sword")
    assert sword is not None and sword.damage == (4, 7)
    assert inventory.take(w, g.inventories["Drew"], sword, chest).ok
    random.seed(3)
    dmgs = {combat.strike("Drew", "X", {"X": 100}, "sword", sword.damage)["damage"] for _ in range(50)}
    assert min(dmgs) >= 4 and max(dmgs) <= 7
