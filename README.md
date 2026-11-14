# Zoairk

## Example review webapp

Import `examples.json`, review the **reasoning and ordered tool calls**, and approve or deny each example. The interface adapts to desktop and mobile browsers. No model/API credentials or backend service are needed; reviews stay in the current browser's IndexedDB.

### Run

With Node.js 18 or newer installed, run these commands from this repository:

```sh
npm start
```

Open http://localhost:3000. No dependency install is required to run the app. To use a phone on the same Wi-Fi, run `npm run start:lan` and open the printed LAN URL on the phone. Allow private-network access if Windows Firewall asks. School/guest Wi-Fi may block connections between devices; use a shared hotspot or host these static files on an HTTPS site in that case. A phone cannot reach this PC through its own `localhost`.

### Review and export

1. Choose **Import examples**, drag a file onto the empty screen, or try **Load sample**.
2. Read the player input, always-visible reasoning, and numbered calls. Add an optional review note; approve or deny.
3. Download **Needle training** (`needle-approved.jsonl`) for approved examples only, or **Classifier training** (`classifier-labeled.jsonl`) for both review labels.
4. Download **Save review session** to back up decisions or transfer them to another browser/device, then import that file there. This is manual file transfer, not live synchronization. Use one review tab per browser at a time.

Needle records preserve `query`, `tools`, `reasoning`, and `answers`, with no review fields. Classifier records preserve the same fields and add `label` (`"approve"` or `"deny"`) and `review_reason`. The label applies to the complete proposed output, including reasoning. Pending examples appear in neither training export. Denied outputs are never Needle targets. This app prepares datasets; it does not train models.

Imports accept an array, `{ "examples": [...] }`, a single example, or JSONL, up to 10 MB / 10,000 examples. Tool calls are checked against their declared required argument names and basic types before import. Reasoning is preserved verbatim; absent reasoning displays as missing and exports as an empty string. A structurally valid example can still be semantically incorrect and needs human review. Exact duplicate examples are skipped, and existing decisions are retained. Undo works during the current visit; reviewed examples can also be returned to pending after a reload. Imports never overwrite or delete the source file.

The sample `examples.json` contains the original 10 records as a JSON array. An example has this shape:

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
