"""Integration test: start server.py, talk to it over WebSocket and HTTP."""

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest
import websockets

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for_port(port, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.1)
    raise TimeoutError(f"port {port} never opened")


@pytest.fixture(scope="module")
def server():
    ws_port, http_port = free_port(), free_port()
    env = dict(os.environ, ZOAIRK_STUB="1", ZOAIRK_MIN_TURN_GAP="0",
               ZOAIRK_WS_PORT=str(ws_port), ZOAIRK_HTTP_PORT=str(http_port))
    proc = subprocess.Popen([sys.executable, "server.py"], cwd=ROOT, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        wait_for_port(ws_port)
        wait_for_port(http_port)
        yield ws_port, http_port
    finally:
        proc.terminate()
        proc.wait(timeout=5)


async def recv_json(ws):
    return json.loads(await asyncio.wait_for(ws.recv(), timeout=5))


def test_websocket_intro_and_reply(server):
    ws_port, _ = server

    async def session():
        async with websockets.connect(f"ws://127.0.0.1:{ws_port}") as ws:
            hello = await recv_json(ws)
            assert hello["type"] == "world" and hello["id"]  # world id lets clients reset on restart
            intro = await recv_json(ws)
            assert intro["type"] in ("switch_scene", "message")
            await recv_json(ws)  # stub intro has two messages

            async def narrator_reply():
                # Multiplayer: join lines and the player echo arrive before the narrator's reply.
                while True:
                    m = await recv_json(ws)
                    if m.get("role") == "narrator":
                        return m

            await ws.send(json.dumps({"type": "send_message", "text": "hello"}))
            reply = await narrator_reply()
            assert reply["type"] == "message"
            assert "hello" in reply["text"]

            # Malformed input is ignored and the connection stays usable.
            await ws.send("not json")
            await ws.send(json.dumps({"type": "send_message", "text": "again"}))
            assert "again" in (await narrator_reply())["text"]

    asyncio.run(session())


def test_http_serves_page(server):
    _, http_port = server
    with urllib.request.urlopen(f"http://127.0.0.1:{http_port}/") as resp:
        assert resp.status == 200
        body = resp.read().decode()
    assert "<title>Zoairk</title>" in body
    assert "app.js" in body


def test_single_port_serves_page_and_game(server):
    ws_port, _ = server
    with urllib.request.urlopen(f"http://127.0.0.1:{ws_port}/") as resp:   # same port as the game
        assert resp.status == 200 and "app.js" in resp.read().decode()
    with pytest.raises(urllib.error.HTTPError):
        urllib.request.urlopen(f"http://127.0.0.1:{ws_port}/../server.py")


@pytest.fixture(scope="module")
def limited_server():
    ws_port, http_port = free_port(), free_port()
    env = dict(os.environ, ZOAIRK_STUB="1", ZOAIRK_MIN_TURN_GAP="30",
               ZOAIRK_WS_PORT=str(ws_port), ZOAIRK_HTTP_PORT=str(http_port))
    proc = subprocess.Popen([sys.executable, "server.py"], cwd=ROOT, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        wait_for_port(ws_port)
        yield ws_port
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_rate_limit_slows_spam(limited_server):
    async def session():
        async with websockets.connect(f"ws://127.0.0.1:{limited_server}/?lobby=spam") as ws:
            await ws.send(json.dumps({"type": "send_message", "text": "one"}))
            await ws.send(json.dumps({"type": "send_message", "text": "two"}))
            seen = []
            try:
                while True:
                    seen.append(await recv_json(ws))
            except (asyncio.TimeoutError, TimeoutError):
                pass
            texts = " ".join(m.get("text", "") for m in seen)
            assert "Slow down" in texts and "said: one" in texts and "said: two" not in texts
    asyncio.run(session())


def test_invite_returns_lobby_link_and_qr(server):
    ws_port, _ = server
    with urllib.request.urlopen(f"http://127.0.0.1:{ws_port}/invite?lobby=Red%20Team!") as resp:
        data = json.loads(resp.read())
        assert resp.headers["Access-Control-Allow-Origin"] == "*"
    assert data["lobby"] == "redteam" and data["url"].endswith("/?lobby=redteam")
    assert data["reachable"] is False            # bound to 127.0.0.1: only this computer can use it
    assert data["svg"] is None or data["svg"].lstrip().startswith(("<?xml", "<svg"))


def test_share_url_rules(monkeypatch):
    import types
    import server as srv
    req = lambda host, **h: types.SimpleNamespace(headers={"Host": host, **h})
    monkeypatch.setattr(srv, "PUBLIC_URL", "https://zoairk.example.com")
    assert srv.share_url(req("127.0.0.1:8765"), "red") == ("https://zoairk.example.com/?lobby=red", True)
    monkeypatch.setattr(srv, "PUBLIC_URL", "")
    assert srv.share_url(req("192.168.1.20:8765"), "red") == ("http://192.168.1.20:8765/?lobby=red", True)
    assert srv.share_url(req("x.trycloudflare.com", **{"X-Forwarded-Proto": "https"}), "a")[0] == \
        "https://x.trycloudflare.com/?lobby=a"
    monkeypatch.setattr(srv, "HOST", "0.0.0.0")
    monkeypatch.setattr(srv, "lan_ip", lambda: "10.0.0.5")
    assert srv.share_url(req("localhost:8765"), "red") == (f"http://10.0.0.5:{srv.WS_PORT}/?lobby=red", True)


def test_share_url_keeps_proxy_path(monkeypatch):
    """Drew's deployment: https://www.byui-ai-society.site/zoairk/ behind a proxy."""
    import types
    import server as srv
    monkeypatch.setattr(srv, "PUBLIC_URL", "")
    req = types.SimpleNamespace(headers={"Host": "127.0.0.1:8765"})          # what the proxy forwards
    page = "https://www.byui-ai-society.site/zoairk/"
    assert srv.share_url(req, "test4", page) == ("https://www.byui-ai-society.site/zoairk/?lobby=test4", True)
    prefixed = types.SimpleNamespace(headers={"Host": "www.byui-ai-society.site", "X-Forwarded-Proto": "https",
                                              "X-Forwarded-Prefix": "/zoairk"})
    assert srv.share_url(prefixed, "a")[0] == "https://www.byui-ai-society.site/zoairk/?lobby=a"
    monkeypatch.setattr(srv, "PUBLIC_URL", "https://www.byui-ai-society.site/zoairk")
    assert srv.share_url(req, "b")[0] == "https://www.byui-ai-society.site/zoairk/?lobby=b"


@pytest.fixture(scope="module")
def prefixed_server():
    ws_port, http_port = free_port(), free_port()
    env = dict(os.environ, ZOAIRK_STUB="1", ZOAIRK_MIN_TURN_GAP="0", ZOAIRK_LOG_SYNC_MINUTES="0",
               ZOAIRK_BASE_PATH="/zoairk", ZOAIRK_WS_PORT=str(ws_port), ZOAIRK_HTTP_PORT=str(http_port))
    proc = subprocess.Popen([sys.executable, "server.py"], cwd=ROOT, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        wait_for_port(ws_port)
        yield ws_port
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_serves_under_prefix_whether_or_not_proxy_strips_it(prefixed_server):
    for path in ("/zoairk/", "/zoairk/app.js", "/", "/app.js"):      # kept prefix, and stripped prefix
        with urllib.request.urlopen(f"http://127.0.0.1:{prefixed_server}{path}") as resp:
            assert resp.status == 200
    with urllib.request.urlopen(f"http://127.0.0.1:{prefixed_server}/zoairk/invite?lobby=x") as resp:
        assert json.loads(resp.read())["lobby"] == "x"

    async def session():   # the game socket also answers on the prefixed path, like Drew's client uses
        async with websockets.connect(f"ws://127.0.0.1:{prefixed_server}/zoairk/?lobby=p&name=Z") as ws:
            assert (await recv_json(ws))["type"] == "world"
    asyncio.run(session())
