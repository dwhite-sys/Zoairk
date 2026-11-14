# Zoairk

**Zork, with AI in the middle.** A real-time, multiplayer text adventure where you type anything in plain
English, an authoritative state machine decides what actually happens, and every NPC reacts with its own
memory and personality: doing nothing, **expressing** (body language), or **engaging** (speaking, giving,
or fighting back).

## Play

```sh
# 1. Model: DeepSeek V4.1 Flash through a local Ollama endpoint (signed in to Ollama)
ollama pull deepseek-v4.1-flash:cloud
# 2. Server (Python 3.10+)
pip install -r requirements.txt
python3 server.py            # add ZOAIRK_HOST=0.0.0.0 to let others on your network join
```

Open http://127.0.0.1:8000/?name=YourName. Open a second tab with another name to play together.

**Try:** `open the mailbox` · `take the leaflet` · `read the leaflet` · `light the match and set the mailbox on fire` ·
`"Hello, Jerry!"` · `punch Jerry` · `go north` · `open the chest` · `take the sword from the chest` ·
`attack Jerry with the sword` · `"Joe, hand over that potion!"` · `drink the health potion` · `inventory` · `health` ·
`respawn` · `look`

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
  they carry and hand items over when threatened or paid.
- **Asynchronous multiplayer.** One shared world, a FIFO queue of player inputs, per-player rooms (you see only
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
