from engine import npc as npc_mod
from engine.game import Game


def _game():
    g = Game("worlds/demo.json")
    g.world.save = lambda *a, **k: None
    g.intro("D")
    return g


def test_steal_can_succeed_or_fail_and_moves_item(monkeypatch):
    g = _game()
    npcs = g.world.current.npcs
    jerry = next(n for n in npcs if n.name == "Jerry")
    monkeypatch.setattr(npc_mod, "judge_theft", lambda n, a: False)   # NPC keeps it
    e = g._steal("D", "hammer", "Jerry", npcs)
    assert not e.ok and any(i.properties.name == "hammer" for i in jerry.inventory)
    monkeypatch.setattr(npc_mod, "judge_theft", lambda n, a: True)    # NPC lets go
    e = g._steal("D", "Jerry's hammer", "", npcs)
    assert e.ok and [o.properties.name for o in g.inventories["D"]] == ["hammer"]
    assert not jerry.inventory


def test_steal_partial_item_name(monkeypatch):
    monkeypatch.setattr(npc_mod, "judge_theft", lambda n, a: False)
    g = _game()
    e = g._steal("D", "potion", "Joe", g.world.current.npcs)
    assert e is not None and e.target == "health potion"
