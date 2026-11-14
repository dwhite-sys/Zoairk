# Zoairk engine contracts (frozen 2026-11-14 13:25 MST)

Each piece is built against these. If one must change, change it here first and tell everyone.

## C1: model → engine (`engine/parser.py`)
- Model: `deepseek-v4.1-flash:cloud` via Ollama at `http://127.0.0.1:11434/api/chat`, `think: false`,
  `temperature: 0`, tools = repo `tools.json` (`enter_command(instrument?, action, target)`).
- `parse(text: str, world: World) -> list[ActionSet]`: ordered as they happen. Resolves names against
  visible objects (aliases, case, articles). Unknown target or unknown action: dropped (no state change).
- Quoted text (`"..."`) is speech: `parse` returns `[]`; the game routes it to NPC memory.
- Verb normalisation to handler keys: ignite, extinguish, open, close, read, break_object, throw, examine
  (e.g. light/burn/set on fire → ignite; smash/shatter → break_object; put out → extinguish).

## C2: engine → narrator (`engine/interactions.py`)
- Every handler returns `Event(action, ok, target, instrument, changed, message)`, never prints.
- `changed` is `{"<object>.<state>": new_value}`, e.g. `{"mailbox.on_fire": True}`.

## C3: NPC gauge (`engine/npc.py`)
- `decide(npc: Npc, event_text: str) -> NpcDecision` via tool `npc_decide(decision, confidence, expression?)`,
  decision ∈ {nothing, express, engage}. Invalid → `nothing`.
- `gauge(npcs, event_text) -> list[NpcDecision]`: concurrent calls; rank by confidence; then
  bias + noise (decided 13:20): noisy = confidence + N(0, 0.15); the best noisy engage keeps engage, other
  engages and any noisy engage < 0.5 become express (replaces the board's placeholder `rand(0,1)`).
- `engage(npc, event_text) -> str`: the NPC's spoken or acted reply (chat model with profile + memory).
- Memory: append-only per NPC: `{"turn", "kind": speech|action|inaction|expression|engagement, "text"}`.

## C4: WebSocket (`server.py` ↔ `web/`)
- Client → server: `{"type": "send_message", "text": "..."}`
- Server → client: `{"type": "message", "role": "narrator"|"npc"|"system", "npc"?: name, "text": "...",
  "decision"?: "express"|"engage", "confidence"?: n}`
- Server → client: `{"type": "switch_scene", "scene": name, "description": "..."}`
- Multiplayer (decided 13:18): one shared world for all connections; inputs go through a FIFO queue,
  applied one at a time; every result is broadcast with a `"player"` field. Client connects with
  `ws://127.0.0.1:8765/?name=<player>`. Server → client also sends `{"type":"message","role":"player",
  "player":name,"text":input}` for each queued input, and `role: "system"` join/leave lines.
- Server: `ws://127.0.0.1:8765`. Static web page served from `web/` at `http://127.0.0.1:8000`.

## C5: world JSON (`worlds/*.json`)
```json
{"name": "...", "start_scene": "front_lawn",
 "scenes": {"front_lawn": {"description": "...", "exits": {"north": "house"},
   "objects": [{"name": "mailbox", "aliases": ["box"], "templates": ["openable", "flammable"],
                "description": "...", "text": "optional, for readable"}],
   "npcs": [{"name": "Jerry", "profile": "grumpy blacksmith ..."}]}}}
```
Game state (object states + NPC memory) saves to `saves/<world>.json` after every turn.

## Turn loop (`engine/game.py`, integration)
NPCs run on **player time, not real time** (decided 13:26): every player input gives each NPC in the
scene exactly one turn (nothing / express / engage); NPCs never act on a timer, so they never spam. In
multiplayer the FIFO queue gives each queued input its own NPC round.

input → blank/gibberish? stop (no turn) → quoted? speech to memory → else `parse` → handlers →
`Event`s → `narrate` → message → `gauge` over scene NPCs → express/engage messages → save.
