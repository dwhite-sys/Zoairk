from engine import npc as npc_mod
from engine.game import Game, _third_person


def test_third_person():
    assert _third_person("I grimace", "D") == "D grimaces"
    assert _third_person("I cry into my hands", "D") == "D cries into their hands"
    assert _third_person("I watch Jerry", "D") == "D watches Jerry"
    assert _third_person("shrugs", "D") == "D shrugs"
    assert _third_person("I grimace and back away", "D") == "D grimaces and backs away"


def test_emote_is_narrated_and_witnessed(monkeypatch):
    monkeypatch.setattr(npc_mod, "gauge", lambda *a, **k: [])
    g = Game("worlds/demo.json")
    g.world.save = lambda *a, **k: None
    g.intro("D")
    out = g.handle("*I grimace*", "D")
    assert out[0]["text"] == "*D grimaces*"
    assert "grimaces" in g.world.current.npcs[0].memory[-1]["text"]
