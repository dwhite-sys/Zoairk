from engine.game import Game


def _game(tmp_path):
    g = Game("worlds/demo.json")
    g.world.save = lambda *a, **k: None
    g.intro("D")
    return g


def test_examine_is_read_only_and_describes(tmp_path):
    g = _game(tmp_path)
    turn = g.world.turn
    out = g.handle("check the mailbox", "D")
    assert "closed" in out[0]["text"] and out[0]["private"]
    assert "hammer" in g.handle("inspect jerry", "D")[0]["text"]
    assert "don't see any unicorn" in g.handle("examine the unicorn", "D")[0]["text"]
    assert g.world.turn == turn


def test_examine_hides_unspoken_name(tmp_path):
    g = _game(tmp_path)
    g.handle("north", "D")
    assert "guard" in g.handle("look at the guard", "D")[0]["text"].lower()
    assert "don't see" in g.handle("check theo", "D")[0]["text"]
