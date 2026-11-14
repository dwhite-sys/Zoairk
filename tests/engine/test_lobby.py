import types

import server


def _ws(query):
    return types.SimpleNamespace(request=types.SimpleNamespace(path=f"/?{query}"))


def test_lobby_name_defaults_and_sanitises():
    assert server.lobby_name(_ws("name=Ann")) == "main"
    assert server.lobby_name(_ws("lobby=Team%20Red!")) == "teamred"
    assert server.lobby_name(_ws("lobby=night-run_2")) == "night-run_2"
