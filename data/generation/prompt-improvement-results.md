# Adaptive generation prompt: 200-candidate results

The additional 200 candidates yielded **183 approvals and 17 denials (91.5% approval)** through AI review in the local webapp. There are now 700 reviewed candidates total. All original 500 decisions/notes/timestamps are unchanged.

| Window | Approved | Denied | Approval rate |
|---|---:|---:|---:|
| Original 500, all sources | 422 | 78 | 84.4% |
| Prior generated 400 (batches 07–26) | 329 | 71 | 82.25% |
| New adaptive 200 (batches 27–33) | 183 | 17 | 91.5% |

| Batch | Candidates | Prompt | Approved | Denied |
|---|---:|---|---:|---:|
| 27 | 20 | generation-v2 | 19 | 1 |
| 28 | 20 | generation-v2 | 18 | 2 |
| 29 | 20 | generation-v3 | 19 | 1 |
| 30 | 20 | generation-v3 | 20 | 0 |
| 31 | 20 | generation-v3 | 19 | 1 |
| 32 | 50 | generation-v5 | 45 | 5 |
| 33 | 50 | generation-v6 | 43 | 7 |

## What changed

Reorganized the prompt into a strict four-section annotation contract, with complete corrected examples. Reinforced literal tuple markers, source-order extraction versus execution-order calls, literal intent cues and temporal clues, tool selection by syntax, self instruments, direct objects and part ownership, and independent committed follow-ups after simulation. Later revisions address contextual materials/spatial relations, novelty, unresolved argument pronouns, measuring-tool roles, hypothetical access and repetitive mixed-query templates. See `scripts/generation_rules.md` for the current prompt and `scripts/prompts/` for snapshots.

## Scale trial and limits

The first 50-example attempt completed normally but repeated two prior queries. Its entire response was excluded before ingestion; the failure and token usage are recorded in `prompt-improvement-run.json`. The complete retry was reviewed, with no selective rewriting or semantic filtering of entered candidates. Both accepted 50-example responses are reported separately above. Larger responses fit the increased output budget; the generator now supports up to 50 per invocation. 100-example responses were not tested.

Approval rates measure AI acceptance against the annotation rules, not downstream Needle model accuracy. This adaptive, non-randomized comparison includes evolving prompts and saved denial feedback; it does not isolate the system prompt as the sole cause. Comparable tool-type proportions and call-count averages help track difficulty but do not prove equal semantic difficulty. Repetitive sentence structure is tracked as a diversity concern even when individual candidates are correct. Keep reviewing at 50 per batch before moving to 100 or accepting 5,000 without review.

## Verification

All 700 candidates are unique and reviewed. Canonical classifier labels/notes match the session, and the Needle export contains exactly approved examples. Prior 500 session entries are unchanged. Candidate batches remain immutable; reviews are explicitly labeled AI review (Codex).

The final 200 have tool-type counts {'enter_command': 65, 'check': 60, 'check/enter_command': 75} and average 2.21 calls per query. The first 100 matched the previous tool-type proportions exactly; the larger responses drifted toward more action-only examples, so the final prompt reinforces the allocation. The final ownership/ambiguity/count refinement was added after reviewing batch 33 and has not yet been generation-tested. The latest tested snapshot is generation-v6.md.
