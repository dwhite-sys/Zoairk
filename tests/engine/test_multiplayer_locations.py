"""Each player has their own location: one player moving does not move anyone else (no model calls)."""
from engine.game import Game


def test_players_move_independently():
    g = Game("worlds/demo.json")
    g.intro("Dawson"); g.intro("Drew")
    out = g.handle("go north", player="Drew")
    assert out[0]["type"] == "switch_scene" and out[0]["scene"] == "house" and out[0]["private"]
    assert g.locations == {"Dawson": "front_lawn", "Drew": "house"}
    look = g.handle("look", player="Dawson")[0]["text"]
    assert "front lawn" in look and "dusty front hall" not in look
    assert "dusty front hall" in g.handle("look", player="Drew")[0]["text"]


def test_leave_and_arrive_notices_go_to_the_right_rooms():
    g = Game("worlds/demo.json"); g.intro("Dawson"); g.intro("Drew")
    out = g.handle("go north", player="Drew")
    notices = {m["text"]: m["to_scene"] for m in out if "to_scene" in m}
    assert notices == {"Drew heads north.": "front_lawn", "Drew arrives.": "house"}
    assert all(m.get("others_only") for m in out if "to_scene" in m)
