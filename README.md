# Zoairk

## Game frontend

The game menu, world builder, and WebSocket adventure terminal live in [`frontend-app/`](frontend-app/).

```sh
cd frontend-app
npm start
```

Open http://localhost:3001. The backend runs separately; configure its WebSocket URL in the header. See the [frontend README](frontend-app/README.md) for the hierarchical world format, streaming protocol, and tests.

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
