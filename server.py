"""Zoairk server: WebSocket game channel plus a static file server for web/.

    python3 server.py
    WebSocket: ws://127.0.0.1:8765   (protocol: docs/contracts.md section C4)
    Web page:  http://127.0.0.1:8000

Each browser connection gets its own Game. Game.handle() may make slow LLM
calls, so it runs in a worker thread to keep the event loop responsive.
"""

import asyncio
import functools
import http.server
import json
import os
import threading

import websockets

HOST = "127.0.0.1"
WS_PORT = int(os.environ.get("ZOAIRK_WS_PORT", 8765))
HTTP_PORT = int(os.environ.get("ZOAIRK_HTTP_PORT", 8000))
ROOT = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(ROOT, "web")


class StubGame:
    """Stand-in used until engine/game.py exists, or when ZOAIRK_STUB=1."""

    def intro(self):
        return [
            {"type": "switch_scene", "scene": "stub", "description": "A placeholder room."},
            {"type": "message", "role": "system", "text": "Engine not loaded: running the stub game."},
        ]

    def handle(self, text):
        return [{"type": "message", "role": "narrator", "text": f"You said: {text}"}]


def make_game():
    """Create the real Game if the engine is importable, otherwise the stub."""
    if os.environ.get("ZOAIRK_STUB") == "1":
        return StubGame()
    try:
        from engine.game import Game
    except ImportError as exc:
        print(f"[server] engine.game unavailable ({exc}); using stub game")
        return StubGame()
    return Game()


async def send_all(ws, messages):
    for message in messages or []:
        await ws.send(json.dumps(message))


async def play(ws):
    """One connection = one game session."""
    loop = asyncio.get_running_loop()
    game = await loop.run_in_executor(None, make_game)
    await send_all(ws, await loop.run_in_executor(None, game.intro))

    async for raw in ws:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if data.get("type") != "send_message":
            continue
        text = str(data.get("text", ""))
        try:
            replies = await loop.run_in_executor(None, game.handle, text)
        except Exception as exc:  # keep the connection alive if one turn fails
            print(f"[server] game.handle failed: {exc!r}")
            replies = [{"type": "message", "role": "system", "text": "Something went wrong with that turn."}]
        await send_all(ws, replies)


def start_http_server():
    """Serve web/ in a background thread using the standard library."""
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=WEB_DIR)
    httpd = http.server.ThreadingHTTPServer((HOST, HTTP_PORT), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


async def main():
    start_http_server()
    async with websockets.serve(play, HOST, WS_PORT):
        print(f"[server] web page  http://{HOST}:{HTTP_PORT}", flush=True)
        print(f"[server] websocket ws://{HOST}:{WS_PORT}", flush=True)
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    os.chdir(ROOT)  # so the engine finds worlds/ and saves/ relative to the repo
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
