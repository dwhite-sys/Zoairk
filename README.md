# Zoairk

**Zork, with AI in the middle.** A real-time, multiplayer text adventure where you type anything in plain
English, an authoritative state machine decides what actually happens, and every NPC reacts with its own
memory and personality: doing nothing, **expressing** (body language), or **engaging** (speaking, giving,
or fighting back).

## Quick start

You need **Python 3.10+**, **git**, and **Ollama** (https://ollama.com/download). The game uses
DeepSeek V4.1 Flash, a cloud model served through your local Ollama, so you also need a free Ollama
account (heavier use may need a paid Ollama plan).

```sh
# 1. Get the code
git clone https://github.com/dwhite-sys/Zoairk.git
cd Zoairk

# 2. Set up the model (one time)
ollama signin                          # opens a browser to sign in to your Ollama account
ollama pull deepseek-v4.1-flash:cloud
ollama serve                           # skip if the Ollama app is already running (it listens on 127.0.0.1:11434)

# 3. Install and start the game server (in a second terminal, from the Zoairk folder)
python3 -m venv .venv
source .venv/bin/activate              # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python3 server.py
```

Open **http://127.0.0.1:8765/** in a browser (http://127.0.0.1:8000/ also works). You are asked for your name, then for a lobby.

### Lobbies and multiplayer

- Type a lobby name to create it, or the name of an existing lobby to join it. Each lobby has its own
  world and its own save. A blank lobby name joins `main`.
- After you join, the address bar shows a link like `http://127.0.0.1:8000/?lobby=red&name=Ann`.
  Share it (changing the name) so friends land in the same lobby.
- To play together on one machine, open a second browser tab with a different name and the same lobby.
- **To let others on your network join**, start the server with `ZOAIRK_HOST=0.0.0.0 python3 server.py`.
  It prints the address to share, e.g. `http://192.168.1.20:8000/?lobby=red`.
  Ports: 8000 (web page) and 8765 (game WebSocket); change them with `ZOAIRK_HTTP_PORT` and `ZOAIRK_WS_PORT`.

### Hosting it for others (one link, nothing to install for players)

**Full step-by-step guide: [docs/HOSTING.md](docs/HOSTING.md)** — what the server and the client are, LAN vs
domain vs tunnel, running it as a service, and the play-log sync.

The game server serves the web page and the game on **one port** (8765 by default), so a single address is
all players need, on a phone or a computer.

```sh
ZOAIRK_HOST=0.0.0.0 python3 server.py     # listen on all interfaces; players open http://<server-ip>:8765/
```

Put it behind your domain with any HTTPS reverse proxy that passes WebSocket upgrades. The page switches to
`wss://` automatically when served over HTTPS. For example, with Caddy:

```
zoairk.example.com {
    reverse_proxy 127.0.0.1:8765
}
```

Or skip the proxy and use a tunnel: `cloudflared tunnel --url http://127.0.0.1:8765`, or
`tailscale funnel 8765`.

Every turn calls the model on the host's Ollama account, so the server has built-in limits. Set them with
environment variables:

| Variable | Default | Meaning |
|---|---|---|
| `ZOAIRK_MIN_TURN_GAP` | `2` | seconds between one player's turns |
| `ZOAIRK_MAX_PENDING` | `12` | queued turns per lobby |
| `ZOAIRK_MAX_PLAYERS` | `8` | players per lobby |
| `ZOAIRK_MAX_LOBBIES` | `20` | lobbies per server |
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | which Ollama to use |
| `ZOAIRK_MODEL` | `deepseek-v4.1-flash:cloud` | which model to use |
| `ZOAIRK_WS_PORT` / `ZOAIRK_HTTP_PORT` | `8765` / `8000` | ports (8000 is the older page-only port) |

To take it down, stop `server.py`. Restarting starts every lobby fresh, and open pages reset themselves.

### Play logs (free play-testing data)

Every turn is logged to `logs/<date>.jsonl`: lobby, player, room, what they typed, every reply (narration, each
NPC's decision and confidence), turn time, errors, and whether "Nothing happens" came back. Joins, leaves and
world events (fires burning out) are logged too. `logs/` is git-ignored because it holds player names and inputs.
Every 10 minutes the server pushes an **anonymized** copy (names replaced by stable IDs like `player-3fa2c1`) to the
`play-logs` branch, so the whole team can review real play; see [docs/HOSTING.md](docs/HOSTING.md#4-play-logs-free-play-testing).

```sh
python3 tools/log_report.py                  # turns, success rate, errors, timing, NPC decisions
python3 tools/log_report.py --lobby play     # one lobby
```

The report lists every input that got "Nothing happens" and every error: those are the next parser and world
fixes. Set `ZOAIRK_LOG_DIR` to log somewhere else.

### How to play

Type what you want to do in plain English and press Enter.

| You want to… | Type, for example |
|---|---|
| Look around / at something | `look` · `examine the mailbox` · `check Jerry` |
| Act on the world | `open the mailbox` · `read the leaflet` · `light the match and set the mailbox on fire` |
| Move | `north` · `go south` (or `n`, `s`, `e`, `w`) |
| Pick up, drop, store, give | `take the rock` · `drop the rock` · `put the leaflet in the mailbox` · `give the coin to Joe` |
| Talk (quotes = speech) | `"Hello, Jerry!"` · `"Joe, how much for a potion?"` |
| Emote (asterisks) | `*I grimace and back away*` |
| Fight | `punch Jerry` · `attack the guard with the sword` · `throw the rock at Joe` |
| Threaten, steal, buy | `"Hand over that potion or else"` · `steal Jerry's hammer` · pay Joe the gold coin from the chest |
| After a fight | `loot Jerry` (a dead NPC) · `loot Drew` (where a player fell) · `respawn` when you die |
| Check yourself | `inventory` (or the 🎒 button) · `health` |

Tips: the house to the north has a chest (a sword and a gold coin) and a sleepy guard. NPCs remember what you
did to them, even after you leave and come back, and even after you die and respawn.

### Troubleshooting

- **"Something went wrong with that turn"** or no replies: make sure Ollama is running and signed in
  (`ollama list` should show `deepseek-v4.1-flash:cloud`).
- **Page loads but says "reconnecting…"**: the game server is not running; start `python3 server.py`.
- **Restarting the server** starts fresh worlds; open pages reset themselves automatically.
- Run the tests with `python3 -m pytest -q tests/engine` (no model needed for most tests).

## What it does

- **Natural-language actions → tool calls.** The model turns player text into ordered
  `enter_command(instrument, action, target)` calls (the same schema as the Needle dataset below).
  Quoted text is speech; gibberish and blank input change nothing.
- **Authoritative state machine.** Object states (open, on fire, broken, burnt to ash), inventories with
  weight rules, containers (mailbox, chest), combat with per-weapon damage, health, death, respawn and looting
  live in Python, not in the model. The model narrates what the engine decided.
- **NPCs that remember.** Each NPC decides nothing / express / engage with a confidence (bias plus noise, so it
  feels alive). They remember who said and did what: leave and come back, and Jerry still knows you punched him,
  or that he killed you. Strangers are "the guard" until they tell you their name. NPCs can fight back with what
  they carry, hand items over when threatened or paid, and decide for themselves whether to let a thief get
  away with something. What they say matches what the game actually does.
- **Role-play.** Speak in quotes, emote in asterisks (`*I grimace*`), examine anything, or act out free-form
  moves at an NPC; they see it and react.
- **Lobbies.** Create or join a named lobby; each has its own world and save.
- **Asynchronous multiplayer.** Within a lobby, one shared world, a FIFO queue of player inputs, per-player rooms (you see only
  your room), arrival and departure notices. NPCs act on player time, one turn each per input.
- **A world that moves on its own.** Fires burn out to ash after a random time even if nobody acts.
- **Feels like a game.** Synthesized sound effects (no audio files), fire glow, hit shake for the player who was
  hit, a health bar and an inventory overlay.

## How it works

```
player text → parser (DeepSeek, enter_command tool calls) → state machine (objects, inventory, combat)
           → events → narrator (DeepSeek) → WebSocket → every player in the room
           → NPC gauge: npc_decide(nothing|express|engage, confidence, attack?, give?) per NPC → memory
world clock (every 5 s): fires burn out → broadcast
```

Code: `engine/` (game loop, parser, interactions, inventory, combat, NPCs, narrator, world), `server.py`
(WebSocket + static web), `web/` (UI and effects), `worlds/demo.json` (the demo world), `docs/contracts.md`
(the interfaces between parts). Tests: `python3 -m pytest -q tests/engine`.

The object system and interactions build on the team's earlier `nlp_state_machine` engine.

---

## Example review webapp

The standalone browser review app lives in [`review-app/`](review-app/). It imports JSON examples, displays reasoning and ordered tool calls, and exports approved Needle examples and labeled classifier data.

```sh
cd review-app
npm start
```

Open http://localhost:3000. For phone access on the same network, run `npm run start:lan` from that folder. See the [app README](review-app/README.md) for the input format, exports, persistence, and testing instructions.

## Needle seed dataset

Training examples for parsing natural-language actions into temporally ordered `enter_command(instrument, action, target)` calls with Needle 3.

## Dataset

- `data/needle3_commands.jsonl`: 10 examples and 25 ordered calls in Cactus's native local fine-tuning format.
- `tools.json`: the `enter_command` JSON schema.
- `examples/example.pretty.json`: one formatted record for inspection.

Each JSONL record contains `query`, `tools`, `reasoning`, and `answers`. The query is the input; the target is reasoning followed by ordered JSON tool calls. There is no prose assistant response or `content` field. The local trainer wraps `reasoning` in `<think>` tags automatically, so the stored field contains the parsing text without those wrappers.

The reasoning preserves phrase-level extraction, temporal markers, ordering relationships, and the final execution sequence. Argument names are `instrument`, `action`, and `target`.

## Local fine-tuning

```sh
pip install "cactus-compute[train]"
cactus finetune data/needle3_commands.jsonl --epochs 10 --batch-size 1 --max-len 2048
cactus build --lora checkpoints/needle_lora.safetensors --out zoairk.cact
```

These commands are a starting point; this repository contains a small seed dataset, not a trained model or an accuracy evaluation. Check rendered token lengths against `--max-len` when expanding the dataset, because the trainer truncates examples exceeding that limit.

Use the native local format to retain `reasoning`: the current local chat-format converter does not copy assistant reasoning into that field.

References: [Cactus](https://github.com/cactus-compute/cactus), [fine-tuning guide](https://cactuscompute.com/blog/finetuning-needle), and [local renderer](https://github.com/cactus-compute/cactus/blob/main/cactus/model/finetune.py).

## Generating and reviewing new batches

See [the Ollama workflow](scripts/OLLAMA_WORKFLOW.md) for generating up to 20 pending candidates at a time, committing them through Git, reviewing them in the local webapp, and committing the saved decisions. AI review notes remain distinct from human review notes.
