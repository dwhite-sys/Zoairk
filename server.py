"""Zoairk server: WebSocket game channel plus a static file server for web/.

    python3 server.py
    WebSocket: ws://127.0.0.1:8765   (protocol: docs/contracts.md section C4)
    Web page:  http://127.0.0.1:8000

Lobbies: ?lobby=<name> joins (or creates) a named lobby with its own world and save; the default
is "main". Within a lobby every connection shares ONE Game. Player inputs go into the lobby's
FIFO queue and a single worker applies them in arrival order, so the state machine never sees two
turns at once (board B4 "FIFO Queue"). Every result is broadcast to all players, tagged with who
acted. Game.handle() makes slow LLM calls, so it runs in a worker thread.
"""

import asyncio
import functools
import http.server
import json
import mimetypes
import os
import time
from datetime import datetime, timezone
import threading
import uuid

import websockets

def _load_env_file(path):
    """Settings from zoairk.env (written by tools/setup_domain.py); real environment variables win."""
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key.strip(), value.strip().strip('"'))
    except FileNotFoundError:
        pass


_load_env_file(os.environ.get("ZOAIRK_ENV_FILE", os.path.join(os.path.dirname(os.path.abspath(__file__)), "zoairk.env")))

HOST = os.environ.get("ZOAIRK_HOST", "127.0.0.1")   # 0.0.0.0 lets other machines on the network join
WS_PORT = int(os.environ.get("ZOAIRK_WS_PORT", 8765))
HTTP_PORT = int(os.environ.get("ZOAIRK_HTTP_PORT", 8000))
ROOT = os.path.dirname(os.path.abspath(__file__))
# Abuse limits for a hosted server (every turn spends model calls).
MIN_TURN_GAP = float(os.environ.get("ZOAIRK_MIN_TURN_GAP", 2.0))   # seconds between one player's turns
MAX_PENDING = int(os.environ.get("ZOAIRK_MAX_PENDING", 12))        # queued turns per lobby
MAX_LOBBIES = int(os.environ.get("ZOAIRK_MAX_LOBBIES", 20))
MAX_PLAYERS = int(os.environ.get("ZOAIRK_MAX_PLAYERS", 8))         # per lobby
# Interaction log: one JSON line per turn and per world event, for reviewing what works and what doesn't.
LOG_DIR = os.environ.get("ZOAIRK_LOG_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs"))
LOG_SYNC_MINUTES = float(os.environ.get("ZOAIRK_LOG_SYNC_MINUTES", 10))   # push anonymized logs to git; 0 = off
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


class Lobby:
    """One named lobby: its own world, save file, FIFO queue, players and turn worker."""

    def __init__(self, name: str):
        self.name = name
        self.game = make_game()
        world = getattr(self.game, "world", None)
        if world is not None:
            world.save_name = f"lobby_{name}"      # each lobby keeps its own save
        self.world_id = uuid.uuid4().hex           # changes when a lobby is (re)created, so clients reset
        self.players: dict = {}                    # websocket -> player name
        self.queue: asyncio.Queue = asyncio.Queue()
        self.current_actor = None                  # the player whose turn is being broadcast
        asyncio.create_task(turn_worker(self))


LOBBIES: dict[str, Lobby] = {}


def lobby_for(name: str) -> Lobby:
    """Join the named lobby, creating it (a fresh world) the first time anyone uses the name."""
    if name not in LOBBIES:
        LOBBIES[name] = Lobby(name)
        print(f"[server] created lobby {name!r}", flush=True)
    return LOBBIES[name]


async def broadcast(lobby, messages, scene=None):
    """Deliver each message to the right players in this lobby.

    - switch_scene / private: only the player it belongs to;
    - to_scene: only players currently in that room (others_only skips the actor);
    - otherwise, with scene: players in that room plus the actor; without scene: everyone.
    """
    locations = getattr(lobby.game, "locations", {})
    for ws in list(lobby.players):
        me = lobby.players[ws]
        mine = []
        for m in messages:
            owner = m.get("player")
            if (m.get("type") == "switch_scene" or m.get("private")) and owner not in (None, me):
                continue
            if "to_scene" in m:
                if locations.get(me) != m["to_scene"] or (m.get("others_only") and owner == me):
                    continue
            elif scene is not None and locations.get(me, scene) != scene and me != lobby.current_actor:
                continue
            mine.append(m)
        try:
            await send_all(ws, mine)
        except websockets.ConnectionClosed:
            lobby.players.pop(ws, None)


def log_event(lobby, kind, **fields):
    """Append one record to logs/<date>.jsonl. Logging must never break the game."""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        now = datetime.now(timezone.utc)
        record = {"ts": now.isoformat(timespec="milliseconds"), "lobby": lobby.name,
                  "world": lobby.world_id[:8], "kind": kind, **fields}
        with open(os.path.join(LOG_DIR, f"{now:%Y-%m-%d}.jsonl"), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:
        print(f"[server] log failed: {exc!r}")


def summarize_replies(replies):
    """The parts of a turn worth reviewing: what was said back and how each NPC decided."""
    out = []
    for r in replies or []:
        if r.get("type") == "message":
            item = {"role": r.get("role"), "text": r.get("text")}
            for k in ("npc", "decision", "confidence", "effects", "hit"):
                if r.get(k) not in (None, [], ""):
                    item[k] = r[k]
            out.append(item)
        elif r.get("type") == "switch_scene":
            out.append({"role": "scene_change", "text": r.get("scene")})
    return out


async def log_sync():
    """Every LOG_SYNC_MINUTES, push anonymized logs to the repo's play-logs branch (tools/sync_logs.py)."""
    if LOG_SYNC_MINUTES <= 0:
        return
    import sys
    script = os.path.join(ROOT, "tools", "sync_logs.py")
    while True:
        await asyncio.sleep(LOG_SYNC_MINUTES * 60)
        proc = await asyncio.create_subprocess_exec(sys.executable, script, stdout=asyncio.subprocess.PIPE,
                                                    stderr=asyncio.subprocess.STDOUT,
                                                    env={**os.environ, "ZOAIRK_LOG_DIR": LOG_DIR})
        out, _ = await proc.communicate()
        print(f"[server] log sync: {out.decode().strip()[:200]}", flush=True)


async def world_clock():
    """Asynchronous world events (fire burning out) every few seconds, independent of player input."""
    loop = asyncio.get_running_loop()
    while True:
        await asyncio.sleep(5)
        for lobby in list(LOBBIES.values()):
            tick = getattr(lobby.game, "tick", None)
            if tick is None:
                continue
            try:
                events = await loop.run_in_executor(None, tick, loop.time())
            except Exception as exc:
                print(f"[server] world clock failed in {lobby.name!r}: {exc!r}")
                continue
            if events:
                log_event(lobby, "world", replies=summarize_replies(events))
                await broadcast(lobby, events)


async def turn_worker(lobby):
    """Apply one lobby's queued inputs one at a time, in arrival order (FIFO)."""
    loop = asyncio.get_running_loop()
    game = lobby.game
    while True:
        name, text = await lobby.queue.get()
        lobby.current_actor = name
        here = getattr(game, "locations", {}).get(name)          # room where the turn happens
        await broadcast(lobby, [{"type": "message", "role": "player", "player": name, "text": text}], scene=here)
        started, error = time.monotonic(), None
        try:
            replies = await loop.run_in_executor(None, functools.partial(game.handle, text, player=name))
        except Exception as exc:  # keep everyone connected if one turn fails
            print(f"[server] game.handle failed: {exc!r}")
            error = repr(exc)
            replies = [{"type": "message", "role": "system", "text": "Something went wrong with that turn."}]
        log_event(lobby, "turn", player=name, room=here, input=text,
                  seconds=round(time.monotonic() - started, 2), error=error,
                  nothing_happened=any(r.get("text") == "Nothing happens." for r in replies or []),
                  replies=summarize_replies(replies),
                  player_hp=getattr(game, "player_hp", {}).get(name))
        for r in replies or []:
            r.setdefault("player", name)
        # Players in the room where it happened see it; a player who just moved sees their new room.
        await broadcast(lobby, replies, scene=here)
        lobby.queue.task_done()


def _query(ws, key: str) -> str:
    try:
        from urllib.parse import parse_qs, urlparse
        return parse_qs(urlparse(ws.request.path).query).get(key, [""])[0].strip()[:24]
    except Exception:
        return ""


def player_name(ws, lobby=None) -> str:
    return _query(ws, "name") or f"Player {len(lobby.players) + 1 if lobby else 1}"


def lobby_name(ws) -> str:
    raw = _query(ws, "lobby").lower()
    return "".join(c for c in raw if c.isalnum() or c in "-_") or "main"


async def play(ws):
    """Join a lobby's shared world; every input goes through that lobby's FIFO queue."""
    loop = asyncio.get_running_loop()
    wanted = lobby_name(ws)
    if wanted not in LOBBIES and len(LOBBIES) >= MAX_LOBBIES:
        await ws.send(json.dumps({"type": "message", "role": "system", "text": "The server is full of lobbies; join an existing one."}))
        return
    lobby = lobby_for(wanted)
    if len(lobby.players) >= MAX_PLAYERS:
        await ws.send(json.dumps({"type": "message", "role": "system", "text": f"Lobby {lobby.name} is full ({MAX_PLAYERS} players)."}))
        return
    name = player_name(ws, lobby)
    last_turn = 0.0
    lobby.players[ws] = name
    await ws.send(json.dumps({"type": "world", "id": lobby.world_id, "lobby": lobby.name}))
    await send_all(ws, await loop.run_in_executor(None, functools.partial(lobby.game.intro, name)))
    log_event(lobby, "join", player=name)
    await broadcast(lobby, [{"type": "message", "role": "system", "text": f"{name} joined lobby {lobby.name}."}])
    try:
        async for raw in ws:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if data.get("type") != "send_message":
                continue
            text = str(data.get("text", ""))
            if not text.strip():
                continue
            now = time.monotonic()
            if now - last_turn < MIN_TURN_GAP or lobby.queue.qsize() >= MAX_PENDING:
                await ws.send(json.dumps({"type": "message", "role": "system", "private": True,
                                          "text": "Slow down a moment, the world is still catching up."}))
                continue
            last_turn = now
            await lobby.queue.put((name, text[:500]))
    finally:
        lobby.players.pop(ws, None)
        log_event(lobby, "leave", player=name)
        await broadcast(lobby, [{"type": "message", "role": "system", "text": f"{name} left."}])


PUBLIC_URL = os.environ.get("ZOAIRK_PUBLIC_URL", "").rstrip("/")   # e.g. https://zoairk.your.domain


def lan_ip() -> str | None:
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return None


def share_url(request, lobby: str) -> tuple[str, bool]:
    """The link other people can open for this lobby, and whether they can likely reach it.

    ZOAIRK_PUBLIC_URL wins (a domain or tunnel). Otherwise use the address the browser used, unless that is
    localhost, in which case use this machine's network address when the server listens on the network.
    """
    from urllib.parse import quote
    base, reachable = PUBLIC_URL, True
    if not base:
        host = request.headers.get("X-Forwarded-Host") or request.headers.get("Host") or f"127.0.0.1:{WS_PORT}"
        proto = request.headers.get("X-Forwarded-Proto", "http")
        name = host.rsplit(":", 1)[0].strip("[]")
        if name in ("localhost", "127.0.0.1", "::1") or name.startswith("127."):
            ip = lan_ip() if HOST == "0.0.0.0" else None
            host, reachable = (f"{ip}:{WS_PORT}", True) if ip else (host, False)
        base = f"{proto}://{host}"
    return f"{base}/?lobby={quote(lobby)}", reachable


def invite_response(request):
    """GET /invite?lobby=x -> {url, reachable, svg}: a QR code people scan to join this lobby."""
    from urllib.parse import parse_qs, urlparse
    from websockets.datastructures import Headers
    from websockets.http11 import Response
    raw = parse_qs(urlparse(request.path).query).get("lobby", ["main"])[0].lower()
    lobby = "".join(c for c in raw if c.isalnum() or c in "-_")[:24] or "main"
    url, reachable = share_url(request, lobby)
    svg = None
    try:
        import io
        import segno
        buf = io.BytesIO()
        segno.make(url, error="m").save(buf, kind="svg", scale=6, border=2, dark="#111", light="#fff", xmldecl=False, omitsize=True)
        svg = buf.getvalue().decode()
    except Exception:                      # no QR library: the page still shows the link
        pass
    body = json.dumps({"url": url, "reachable": reachable, "lobby": lobby, "svg": svg}).encode()
    return Response(200, "OK", Headers([("Content-Type", "application/json"), ("Content-Length", str(len(body))),
                                        ("Access-Control-Allow-Origin", "*"), ("Cache-Control", "no-store")]), body)


def process_request(connection, request):
    """Single-port mode: plain HTTP requests get the web page, WebSocket upgrades get the game.

    One port means one link (or one tunnel) is enough for players anywhere, phones included.
    """
    if request.headers.get("Upgrade", "").lower() == "websocket":
        return None
    from urllib.parse import unquote, urlparse
    from websockets.datastructures import Headers
    from websockets.http11 import Response
    if urlparse(request.path).path == "/invite":
        return invite_response(request)
    rel = unquote(urlparse(request.path).path).lstrip("/") or "index.html"
    path = os.path.realpath(os.path.join(WEB_DIR, rel))
    if not path.startswith(os.path.realpath(WEB_DIR) + os.sep) or not os.path.isfile(path):
        return Response(404, "Not Found", Headers([("Content-Type", "text/plain")]), b"Not found")
    with open(path, "rb") as fh:
        body = fh.read()
    ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
    return Response(200, "OK", Headers([("Content-Type", ctype), ("Content-Length", str(len(body))),
                                        ("Cache-Control", "no-cache")]), body)


def start_http_server():
    """Serve web/ in a background thread using the standard library."""
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=WEB_DIR)
    httpd = http.server.ThreadingHTTPServer((HOST, HTTP_PORT), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


async def main():
    lobby_for("main")                     # the default lobby exists from the start
    asyncio.create_task(world_clock())
    asyncio.create_task(log_sync())
    start_http_server()
    async with websockets.serve(play, HOST, WS_PORT, process_request=process_request):
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
        print(f"[server] single-port (page + game, use this for hosting): http://{HOST}:{WS_PORT}", flush=True)
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    os.chdir(ROOT)  # so the engine finds worlds/ and saves/ relative to the repo
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
