# Zoairk

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
