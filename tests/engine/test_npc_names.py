"""Strangers see an unknown NPC by title until it says its name aloud (no model calls)."""
from engine.game import Game, _reveal_or_mask


def test_unknown_npc_masked_until_introduced():
    g = Game("worlds/demo.json")
    theo = g.world.scenes["house"].npcs[0]
    jerry = g.world.scenes["front_lawn"].npcs[0]
    assert jerry.known and not theo.known and theo.label == "the guard"
    assert _reveal_or_mask(theo, "Theo yawns.") == "The guard yawns."
    assert not theo.known
    assert _reveal_or_mask(theo, '"Name\'s Theo," he grunts.').startswith('"Name')
    assert theo.known and theo.label == "Theo"
