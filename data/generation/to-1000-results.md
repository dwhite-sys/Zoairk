# Review run to 1,000 candidates

Added **300 reviewed candidates: 276 approved and 24 denied (92.00% approval)**. Total: **881 approved, 119 denied, zero pending**.

| Window | Approval rate |
|---|---:|
| Prior generated 400 (07–26) | 82.25% |
| Prior adaptive 200 (27–33) | 91.5% |
| This adaptive 300 (34–39) | 92.00% |

| Batch | Prompt | Approved / 50 | Denied |
|---|---|---:|---:|
| 34 | generation-v7 | 48 | 2 |
| 35 | generation-v7 | 49 | 1 |
| 36 | generation-v8 | 37 | 13 |
| 37 | generation-v8 | 46 | 4 |
| 38 | generation-v9 | 50 | 0 |
| 39 | generation-v9 | 46 | 4 |

Prompt refinements addressed literal capitalization, repeated final triples in single-action annotations, inferred instruments from verbs, source/destination ownership, material references, ambiguous spatial references and unwanted modern machinery. The final generation group used a complete single-action example plus the accumulated denial notes. Prompt snapshots and per-batch hashes preserve which instructions were used.

## Generation failures

- 35-first: Example 7: [Finally] absent from literal query (case mismatch or invented clue). 0 candidates entered; full response excluded before ingestion. Entire response excluded before ingestion; retry without semantic repairs.

## Interpretation

All six entered batches contain 50 candidates and were reviewed through the local webapp. Tool mix: {'enter_command': 90, 'check': 90, 'check/enter_command': 120}; mean calls per query: 2.21. Rates describe AI annotation acceptance, not downstream model accuracy. This was an adaptive comparison, not a controlled trial; batch variance and wording differences matter. Do not equate high acceptance with safe unreviewed approval. 50-example generation is tested; 100-example responses remain untested.

## Verification

Exactly 1,000 unique candidates are reviewed. Prior 700 complete review entries (including notes and timestamps) are unchanged. Classifier labels and notes match the session; the Needle export contains precisely approved examples. All candidate files pass the application schema; the 23 application tests pass. No candidate text was silently repaired during review.

The latest tested prompt (generation-v9) yielded 96 approvals out of the final 100 candidates, after the preceding prompt group yielded 83 out of 100. The complete run averaged 92%, compared with 91.5% in the prior adaptive run: a small overall change, not a demonstrated accuracy guarantee. The final prompt fixes were successful on this sample; further reviewed batches are needed to establish consistency. Newly saved denial notes are automatically included in subsequent generation requests.
