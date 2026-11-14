import json
import types

import server
from tools.log_report import report


def test_log_event_and_report(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "LOG_DIR", str(tmp_path))
    lobby = types.SimpleNamespace(name="play", world_id="abcdef123456")
    replies = [{"type": "message", "role": "narrator", "text": "The mailbox burns."},
               {"type": "message", "role": "npc", "text": "Jerry glares.", "npc": "Jerry",
                "decision": "express", "confidence": 0.6}]
    server.log_event(lobby, "turn", player="Ann", input="burn the mailbox", seconds=1.2, error=None,
                     nothing_happened=False, replies=server.summarize_replies(replies))
    server.log_event(lobby, "turn", player="Ann", input="asdf", seconds=0.1, error=None,
                     nothing_happened=True, replies=[])
    lines = [json.loads(l) for f in tmp_path.iterdir() for l in f.read_text().splitlines()]
    assert len(lines) == 2 and lines[0]["lobby"] == "play" and lines[0]["replies"][1]["decision"] == "express"
    text = report(lines)
    assert "Turns: 2" in text and "asdf" in text and "express" in text


def test_log_failure_never_breaks(monkeypatch):
    monkeypatch.setattr(server, "LOG_DIR", "/proc/forbidden/zoairk")
    server.log_event(types.SimpleNamespace(name="x", world_id="y"), "turn", player="A")   # no exception
