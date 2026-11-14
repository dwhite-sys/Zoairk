"""Zoairk server: WebSocket game channel plus a static file server for web/.

    python3 server.py
    WebSocket: ws://127.0.0.1:8765   (protocol: docs/contracts.md section C4)
    Web page:  http://127.0.0.1:8000

Asynchronous multiplayer: every connection shares ONE Game (one world). Player inputs go into a
FIFO queue and a single worker applies them in arrival order, so the state machine never sees two
turns at once (board B4 "FIFO Queue"). Every result is broadcast to all players, tagged with who
acted. Game.handle() makes slow LLM calls, so it runs in a worker thread.
"""

import asyncio
import functools
import http.server
import json
import os
import threading

import websockets

HOST = os.environ.get("ZOAIRK_HOST", "127.0.0.1")   # 0.0.0.0 lets other machines on the network join
WS_PORT = int(os.environ.get("ZOAIRK_WS_PORT", 8765))
HTTP_PORT = int(os.environ.get("ZOAIRK_HTTP_PORT", 8000))
ROOT = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(ROOT, "web")


class StubGame:
    """Stand-in used until engine/game.py exists, or when ZOAIRK_STUB=1."""

    def intro(self, player="You"):
        return [
            {"type": "switch_scene", "scene": "stub", "description": "A placeholder room."},
            {"type": "message", "role": "system", "text": "Engine not loaded: running the stub game."},
        ]

    def handle(self, text, player="You"):
        return [{"type": "message", "role": "narrator", "text": f"{player} said: {text}"}]


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


GAME = None                 # the one shared world
CURRENT_ACTOR = None        # the player whose turn is being broadcast (always sees their own turn)
PLAYERS: dict = {}          # websocket -> player name
QUEUE: asyncio.Queue | None = None


async def broadcast(messages, scene=None):
    """Send to everyone, or (with scene) only to players currently in that room."""
    locations = getattr(GAME, "locations", {})
    for ws in list(PLAYERS):
        if scene is not None and locations.get(PLAYERS[ws], scene) != scene and PLAYERS[ws] != CURRENT_ACTOR:
            continue
        # A scene change belongs only to the player who moved; everyone else keeps their own room.
        mine = [m for m in messages
                if not ((m.get("type") == "switch_scene" or m.get("private")) and m.get("player") not in (None, PLAYERS[ws]))]
        try:
            await send_all(ws, mine)
        except websockets.ConnectionClosed:
            PLAYERS.pop(ws, None)


async def turn_worker():
    """Apply queued inputs one at a time, in arrival order (FIFO)."""
    loop = asyncio.get_running_loop()
    while True:
        global CURRENT_ACTOR
        name, text = await QUEUE.get()
        CURRENT_ACTOR = name
        here = getattr(GAME, "locations", {}).get(name)          # room where the turn happens
        await broadcast([{"type": "message", "role": "player", "player": name, "text": text}], scene=here)
        try:
            replies = await loop.run_in_executor(None, functools.partial(GAME.handle, text, player=name))
        except Exception as exc:  # keep everyone connected if one turn fails
            print(f"[server] game.handle failed: {exc!r}")
            replies = [{"type": "message", "role": "system", "text": "Something went wrong with that turn."}]
        for r in replies or []:
            r.setdefault("player", name)
        # Players in the room where it happened see it; a player who just moved sees their new room.
        await broadcast(replies, scene=here)
        QUEUE.task_done()


def player_name(ws) -> str:
    try:
        from urllib.parse import parse_qs, urlparse
        name = parse_qs(urlparse(ws.request.path).query).get("name", [""])[0].strip()[:24]
    except Exception:
        name = ""
    return name or f"Player {len(PLAYERS) + 1}"


async def play(ws):
    """Join the shared world; every input goes through the FIFO queue."""
    loop = asyncio.get_running_loop()
    name = player_name(ws)
    PLAYERS[ws] = name
    await send_all(ws, await loop.run_in_executor(None, functools.partial(GAME.intro, name)))
    await broadcast([{"type": "message", "role": "system", "text": f"{name} joined."}])
    try:
        async for raw in ws:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if data.get("type") != "send_message":
                continue
            text = str(data.get("text", ""))
            if text.strip():
                await QUEUE.put((name, text))
    finally:
        PLAYERS.pop(ws, None)
        await broadcast([{"type": "message", "role": "system", "text": f"{name} left."}])


def start_http_server():
    """Serve web/ in a background thread using the standard library."""
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=WEB_DIR)
    httpd = http.server.ThreadingHTTPServer((HOST, HTTP_PORT), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


async def main():
    global GAME, QUEUE
    GAME = make_game()
    QUEUE = asyncio.Queue()
    asyncio.create_task(turn_worker())
    start_http_server()
    async with websockets.serve(play, HOST, WS_PORT):
        print(f"[server] web page  http://{HOST}:{HTTP_PORT}", flush=True)
        if HOST == "0.0.0.0":
            import socket
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                    s.connect(("8.8.8.8", 80)); lan = s.getsockname()[0]
                print(f"[server] others on this network: http://{lan}:{HTTP_PORT}", flush=True)
            except OSError:
                pass
        print(f"[server] websocket ws://{HOST}:{WS_PORT}", flush=True)
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    os.chdir(ROOT)  # so the engine finds worlds/ and saves/ relative to the repo
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
