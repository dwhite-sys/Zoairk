# One-batch Ollama → Git → local review → Git workflow

The generator runs only when invoked; it does not loop, train, or approve anything. It uses the configured Ollama OpenAI-compatible endpoint, defaults to `deepseek-v4.1-flash:cloud`, and defaults to 20 pending candidates and supports a reviewed trial of up to 50 per request. A `:cloud` model can consume the user's Ollama cloud allowance.

Feedback is part of every request: the generator rereads the committed review session, sends every saved denial note with its query, and includes approved style examples plus `generation_rules.md` as the system prompt. Commit/pull the latest review exports before the next batch so newly denied examples are visible. Fold recurring failure modes into the rules file. This is prompt feedback, not a model-weight update; do not call it fine-tuning. The reviewer should also read the same rules and denial notes before approving a later batch.

From the repository root, with a clean working tree:

1. `git pull --ff-only origin main`.
2. Check `curl http://localhost:11434/v1/models`. No credentials are committed. If needed, provide `OLLAMA_API_KEY` through the environment.
3. Select the next unused numbered filename and run:

```sh
python3 scripts/generate_review_batch.py \
  --base-url http://localhost:11434/v1 \
  --model deepseek-v4.1-flash:cloud \
  --output data/review/07-examples.json \
  --raw-output /tmp/zoairk-generation-07-response.json
```

The example number above is illustrative: increment it for later batches. Existing output files are never replaced. Inspect failures and the raw response before retrying; do not quietly repair candidate semantics or retry indefinitely. Tools are attached from approved records, and shape/duplicates/source-clue presence are checked before writing. These checks do not establish semantic correctness. Provenance/usage goes in `data/generation/`, outside the served batch directory.

4. Commit only the generator/rules, batch, and provenance you intend to share; push before reviewing. Another clone should pull before loading the batch. This keeps candidate ingestion in Git, rather than hiding it in a browser upload.
5. For local review, start the existing server with a new, untracked runtime state directory. Seed its `state.json` from the latest committed `data/review/exports/zoairk-review-session.json` so older decisions are preserved. Serve ALL numbered batches using `EXAMPLES_DIR`: the server prunes saved records absent from the served dataset on session sync. Serving only the new batch would drop older decisions from the canonical exports. Example environment:

```sh
EXAMPLES_DIR="$PWD/data/review" \
REVIEW_DATA_DIR=/tmp/zoairk-review-07 \
EXPORT_DIR="$PWD/data/review/exports" \
PORT=3018 node review-app/scripts/serve.cjs
```

Create `/tmp/zoairk-review-07` and copy the committed review session to `/tmp/zoairk-review-07/state.json` BEFORE starting the server. Never overwrite an existing state directory. Use a fresh browser origin/port or inspect the queue for stale browser records before reviewing. Open the app in the in-app browser. Review each candidate's input, reasoning and ordered calls. Use notes beginning `AI review (Codex):` for AI decisions; never represent them as human approvals. Deny questionable examples with a concrete correction note. Do not change old decisions.

6. Reload and verify no pending examples from the new batch remain, and the old decisions/notes are unchanged. The server writes all three canonical exports into the repo. Check their diffs; then commit and push the saved decisions. If the remote changed during review, pull/reconcile without dropping either reviewer's work; do not force-push or overwrite unrelated decisions.
7. The hosted machine can pull the candidates and committed review data. Its running shared state lives separately; the hosted agent must merge the committed session through the app's normal session-import flow if it needs the decisions immediately. A Git pull alone does not necessarily replace an already-running server's state file. Do not reset that state.

Keep source batches immutable. Approved training exports exclude denied records and strip review fields. The classifier export retains approval/denial notes. The app's current export naming does not distinguish human from AI approvals, so retain the session/notes for provenance and any later audit. Generate the next batch only after completing the current review, or when the user explicitly asks for additional batches.

## Prompt improvement and larger batches

The adaptive run starting with batch 27 targets 200 additional reviewed candidates (700 total). Prompt snapshots are retained under `scripts/prompts/`; each batch records a rules hash, feedback-session hash/count, model, and output token usage. Prompts may improve between reviewed groups. This is an observational comparison using AI review, not a randomized experiment or a claim of human approval. The prior generated 400 candidates yielded 329 approvals (82.25%); the first revised-prompt 100 yielded 95 approvals (95%) with the same 30% action-only / 30% check-only / 40% mixed proportions and similar calls per query.

A 50-candidate request uses `--count 50` and a larger output budget. Inspect complete output before entering it; record truncation or invalid-response failures rather than hiding them. Keep all entered candidates immutable, including denials. Continue reviewing all examples while testing scale. A high approval rate does not establish that unreviewed auto-approval or 100-candidate responses are reliable. Compare the 50-example trials separately before increasing the configured maximum beyond 50.

The subsequent run to 1,000 reviewed candidates is documented in `data/generation/to-1000-results.md` and `to-1000-run.json`. Six further 50-example batches added 276 approvals / 24 denials (92%); the latest tested prompt produced 96/100 approvals in its final group. Current totals are 881 approved and 119 denied. Preserve the review requirement: the intermediate group regressed, and one malformed source-clue response required a full retry.

## Scaling to 5,000 approved examples

The active target is 5,000 **approved**, not reviewed, examples. The baseline was 881 approvals / 119 denials at commit 8be5a1b. Preserve that history. The app now accepts sessions up to 64 MB (still at most 10,000 candidates), and dataset-directory merging runs once across all files. Review candidates fully, then package the exact immutable records with Codex decisions/notes as a small review-session file. Import through the app normal Import examples control: it adds new reviews or restores pending ones while retaining existing decisions. Verify canonical exports after every imported group and commit/push them. This saves repeated full-workspace writes without skipping review. Record short complete generations (e.g. 49 of 50) accurately if all candidates are retained unchanged. Never discard reviewed denials or imply AI approvals are human.
