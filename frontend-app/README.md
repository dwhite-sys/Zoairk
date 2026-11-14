# Zoairk game frontend

A plain HTML/CSS/JavaScript frontend with a start menu, nested world editor, and WebSocket-driven adventure terminal. This lives in `frontend-app/` (the folder containing the supplied boilerplate).

## Run

From the repository root:

```sh
cd frontend-app
npm start
```

Open http://localhost:3001. No dependency installation is needed to serve the frontend. `npm run start:lan` serves the same files on your local network. Phone users need the printed PC address, not their phone's localhost. Windows Firewall and Wi-Fi client isolation may affect access.

The frontend automatically tries `ws://<page-host>:8000/ws` (`wss://` on HTTPS). Open the connection status in the header to enter another WebSocket endpoint and connect. The backend is a separate service and is **not included in this branch**. An unavailable backend is shown as disconnected; the frontend never fabricates game output or a successful world commit.

## Screens

- The main menu has **Create a game** and **Play a game**. Hash routes (`#/create`, `#/play`) support browser back/forward without losing the current in-memory draft.
- Create one area, then add scenes inside it. Each scene can contain objects, NPCs, and exits. Exits have a name/direction and destination chosen from the existing scenes.
- Objects created inside a scene, NPC, or player stay in that container and carry an explicit `owner: { type, id }`. Names can repeat because IDs identify entities. Removing a container removes its children. Removing a scene leaves incoming exits invalid until the author chooses another destination.
- Create a player below the scenes, add inventory items and optional backstory. The first scene is the starting scene. **Add stats** controls are disabled placeholders; serialized stats are `null`.
- Commit world validates names, exit destinations and ownership, then sends JSON. It waits for `game_created` before reporting success. Duplicate submission is blocked while waiting. A disconnect or timeout reports uncertainty and does not automatically resend the world.
- Play sends `look` when opening the terminal after connecting, using the existing command message format. Subsequent nonempty input is sent as a command. Blank input does nothing. Whether a nonempty command is meaningful, including gibberish, belongs to the backend parser. Arrow keys recall successfully sent commands; disconnected commands stay in the input. Reconnection never replays a player command.

Drafts survive navigation between these screens, not a browser refresh. Persisting an accepted world is the backend's responsibility.

## WebSocket handoff

The existing boilerplate envelopes are retained:

```json
{ "type": "create_game", "payload": { "schemaVersion": 1, "areas": [], "player": {} } }
```

```json
{ "type": "command", "payload": { "command": "look" } }
```

The world payload now distinguishes **areas from scenes**; this replaces the boilerplate's flat scene/area model. Backend compatibility with this new payload needs agreement with the engine team. There is no global unowned objects or NPCs list:

```text
world { schemaVersion: 1, areas: [area], player }
area  { id, name, description, scenes: [scene] }
scene { id, name, description, objects: [object], npcs: [npc], exits: [exit] }
npc   { id, name, description, stats: null, objects: [object] }
player{ id, name, stats: null, objects: [object], backstory, startingSceneId }
object{ id, name, description, state, stats: null, owner: { type, id } }
exit  { id, name, destinationSceneId }
```

Owner types are `scene`, `npc`, and `player`. Provisional object states are `unspecified`, `open`, `closed`, `locked`, `unlocked`, `on`, `off`, `intact`, and `broken`. The list lives in `world.js` and needs confirmation from the engine team. It is a single selected state, not a collection of simultaneous flags.

Accepted incoming messages:

```json
{ "type": "game_created", "message": "World loaded" }
{ "type": "output", "text": "You stand beside the harbor." }
{ "type": "chunk", "text": "The guard " }
{ "type": "chunk", "text": "turns to face you." }
{ "type": "done" }
{ "type": "error", "message": "The world could not be loaded." }
```

`delta`/`stream_chunk` and `output` with `stream: true` also append to the current streamed response; `done`/`stream_end` closes it. Plain-text frames render as separate outputs. `output` can also use a string `output` field. Server content is rendered as text, never HTML. An HTTPS frontend requires a WSS endpoint.

## Test

```sh
npm ci
npm run test:all
```

Tests cover world/ownership logic, a real HTTP/WebSocket transport connection, and desktop/mobile browser flows using installed Microsoft Edge. Playwright and `ws` are development-only dependencies. Tests use ports 3101 and 8083. Screenshots are written under ignored `test-results/`.

The test peer in `tests/fixtures/backend.cjs` validates payloads and emits clearly labeled protocol-test output. It is **not a game engine** and never runs under `npm start`. Automated testing does not establish compatibility with an unavailable real backend or verify its persistence, AI, or gameplay. Real phone hardware and Safari have not been tested.

## Development status — November 14, 2026

Resumed on the local `frontend` branch after the shutdown checkpoint. The complete frontend flow was operated manually against the explicitly labeled protocol test server: area and linked scenes, scene-owned object, NPC inventory, player inventory/backstory, world acknowledgement, streamed output, blank input, and command history.

The manual check found a reconnect bug: changing the WebSocket connection while Play was already open did not request a new scene. The fix starts a fresh `look` request on the new connection without replaying player commands; it also releases a world commit awaiting confirmation on the old connection. A desktop/mobile browser regression test covers reconnection.

Validation: 10 logic/integration checks and 10 desktop/mobile browser checks pass (`npm run test:all`). Screenshots are under ignored `frontend-app/test-results/`. The preview runs from this checkout at http://localhost:3001.

Still pending: the real backend is absent from this branch and nothing was listening on port 8000 during verification. The backend URL, nested world schema, supported state list, and real game persistence/AI need confirmation and integration. The protocol fixture verifies transport, not gameplay. Stats remain the requested placeholders, and the first scene remains the starting scene.

Next: provide the engine's WebSocket contract, integrate it, and repeat the complete demo against the real engine. Current messages and provisional object states are documented above. No changes from this frontend task have been pushed.

Restart from the repository root with `cd frontend-app`, then `npm start`. Install test dependencies with `npm ci` if needed. For protocol-only manual checks, separately run `node tests/fixtures/backend.cjs` and use `ws://127.0.0.1:8082/ws`; restore the real endpoint afterward.
