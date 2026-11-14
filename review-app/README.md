# Zoairk example review


Import `examples.json`, review the **reasoning and ordered tool calls**, and approve or deny each example. The interface adapts to desktop and mobile browsers. No model/API credentials are needed.

Decisions are written to the browser's IndexedDB **and** mirrored to the small Node server in `scripts/serve.cjs`, which keeps one snapshot per browser under `REVIEW_DATA_DIR` (default `~/.local/share/zoairk-review`). That means a reload, another browser, or another device on the same deployment picks up the progress already made. The example files themselves are never uploaded — only the review session, which contains the examples you have already imported plus your decisions.

### Run

With Node.js 18 or newer installed, run these commands from the repository root:

```sh
cd review-app
npm start
```

Open http://localhost:3000. No dependency install is required to run the app. To use a phone on the same Wi-Fi, run `npm run start:lan` and open the printed LAN URL on the phone. Allow private-network access if Windows Firewall asks. School/guest Wi-Fi may block connections between devices; use a shared hotspot or host these static files on an HTTPS site in that case. A phone cannot reach this PC through its own `localhost`.

To serve the app under a path prefix rather than at the site root, set `APP_PREFIX`.

```sh
APP_PREFIX=/needle-training PORT=3000 npm start
```

That serves `/needle-training/` and redirects the bare `/needle-training` to the trailing slash, so the page's relative asset paths resolve. Leave `APP_PREFIX` unset to serve from the root, which is the default.

### Where reviews are stored

Each browser gets an id in IndexedDB and posts its whole session to `POST <prefix>/api/session?client=<id>`, which is validated with the same rules the importer uses and written to `REVIEW_DATA_DIR` / `<id>.json` (temp file plus rename, so a crash cannot leave a half-written snapshot). `GET` on the same route returns every browser's snapshot merged, and the page applies it on load; a browser's own snapshot wins where the same example has conflicting decisions, so local edits and undo always stick. Work done while the server is unreachable stays in IndexedDB and is pushed on the next successful load.

```sh
ls ~/.local/share/zoairk-review      # one snapshot per browser
```

Two known limits, both real:

- **No authentication.** Anyone who can reach the URL can read the merged session and post their own, so put Cloudflare Access (or similar) in front of it if the dataset is sensitive.
- **Last writer wins per browser.** Two people deciding differently on the same example each keep their own choice; there is no conflict resolution beyond that. This is shared progress for one reviewer across devices, not a collaborative editor.

### Review and export

1. Choose **Import examples**, drag a file onto the empty screen, or try **Load sample**.
2. Read the player input, always-visible reasoning, and numbered calls. Add an optional review note; approve or deny.
3. Open **Export datasets**, then download **Needle training** (`needle-approved.jsonl`) for approved examples only, or **Classifier training** (`classifier-labeled.jsonl`) for both review labels.
4. Download **Save review session** to back up decisions or transfer them to another browser/device, then import that file there. This is manual file transfer, not live synchronization. Use one review tab per browser at a time.

Needle records preserve `query`, `tools`, `reasoning`, and `answers`, with no review fields. Classifier records preserve the same fields and add `label` (`"approve"` or `"deny"`) and `review_reason`. The label applies to the complete proposed output, including reasoning. Pending examples appear in neither training export. Denied outputs are never Needle targets. This app prepares datasets; it does not train models.

Imports accept an array, `{ "examples": [...] }`, a single example, or JSONL, up to 10 MB / 10,000 examples. Tool calls are checked against their declared required argument names and basic types before import. Reasoning is preserved verbatim; absent reasoning displays as missing and exports as an empty string. A structurally valid example can still be semantically incorrect and needs human review. Exact duplicate examples are skipped, and existing decisions are retained. Undo works during the current visit; reviewed examples can also be returned to pending after a reload. Imports never overwrite or delete the source file.

The sample `examples.json` contains the current batch as a JSON array. Previous sample batches are preserved in the repository's `past/` directory. Numbered batches in `data/review/` can be served together using `EXAMPLES_DIR`. An example has this shape:

```json
{
  "query": "I unlock the door with my key",
  "tools": [{
    "name": "enter_command",
    "parameters": {
      "type": "object",
      "properties": { "instrument": { "type": "string" }, "action": { "type": "string" }, "target": { "type": "string" } },
      "required": ["instrument", "action", "target"]
    }
  }],
  "reasoning": "Action: unlock; target: door; instrument: key. One action, so no reordering is needed.",
  "answers": [{ "name": "enter_command", "arguments": { "instrument": "key", "action": "unlock", "target": "door" } }]
}
```

### Test

```sh
npm test
npm ci
npm run test:e2e
```

Unit/integration tests need no dependencies. Browser tests use Playwright with installed Microsoft Edge, covering desktop and a touch-enabled mobile viewport, imports, persistence, undo, exports, session transfer, input errors, duplicate imports, safe text rendering, and visible reasoning. To test on a machine without Edge, change `channel: 'msedge'` to an installed Playwright browser channel and install that browser using Playwright. `npm run test:all` runs both test suites. Real phone hardware and Safari are not covered by these automated checks.
