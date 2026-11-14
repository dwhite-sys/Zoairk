"""Integration test: start server.py, talk to it over WebSocket and HTTP."""

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
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
    env = dict(os.environ, ZOAIRK_STUB="1",
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
            intro = await recv_json(ws)
            assert intro["type"] in ("switch_scene", "message")
            await recv_json(ws)  # stub intro has two messages

            await ws.send(json.dumps({"type": "send_message", "text": "hello"}))
            reply = await recv_json(ws)
            assert reply["type"] == "message"
            assert "hello" in reply["text"]

            # Malformed input is ignored and the connection stays usable.
            await ws.send("not json")
            await ws.send(json.dumps({"type": "send_message", "text": "again"}))
            assert "again" in (await recv_json(ws))["text"]

    asyncio.run(session())


def test_http_serves_page(server):
    _, http_port = server
    with urllib.request.urlopen(f"http://127.0.0.1:{http_port}/") as resp:
        assert resp.status == 200
        body = resp.read().decode()
    assert "<title>Zoairk</title>" in body
    assert "app.js" in body
