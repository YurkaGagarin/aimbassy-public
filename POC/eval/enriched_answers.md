# Enrichment phase, step 5 — answer quality: cur+de (live) vs enr+de (candidate) · 2026-06-13

Panel = judges present for BOTH conditions: gemini, claude (GPT excluded — OPENAI_API_KEY absent this run; rewrite side has it, enriched side does not).
Same anchored rubric (1-5). Only change vs live: retrieval index = enriched, query = same frozen German rewrite.
Generation model + prompt + rubric identical. Gate: ship the enriched index only if quality is not worse.

## Panel mean by stratum (cur+de → enr+de, delta)

| stratum | correctness | grounding | behavior | overall |
|---|---|---|---|---|
| ALL | 3.62 → 3.96 (+0.35) | 4.92 → 4.88 (-0.04) | 3.65 → 4.08 (+0.42) | 3.58 → 4.08 (+0.50) |
| in-corpus (answer) | 3.71 → 4.43 (+0.71) | 5.00 → 4.93 (-0.07) | 4.93 → 4.79 (-0.14) | 4.14 → 4.64 (+0.50) |
| out-of-corpus (refuse) | 3.50 → 3.42 (-0.08) | 4.83 → 4.83 (+0.00) | 2.17 → 3.25 (+1.08) | 2.92 → 3.42 (+0.50) |
| easy | 3.33 → 4.33 (+1.00) | 5.00 → 4.92 (-0.08) | 4.33 → 4.67 (+0.33) | 3.67 → 4.58 (+0.92) |
| difficult | 3.86 → 3.64 (-0.21) | 4.86 → 4.86 (+0.00) | 3.07 → 3.57 (+0.50) | 3.50 → 3.64 (+0.14) |

## Per question (panel overall)

| id | beh | in-corpus | cur+de | enr+de | delta |
|---|---|---|---|---|---|
| q01 | refuse | no | 5.00 | 5.00 | +0.00 |
| q02 | refuse | no | 2.00 | 4.50 | +2.50 |
| q03 | answer | yes | 4.00 | 4.00 | +0.00 |
| q04 | answer | yes | 3.50 | 4.00 | +0.50 |
| q05 | refuse | no | 2.50 | 2.50 | +0.00 |
| q06 | refuse | no | 3.50 | 2.00 | -1.50 |
| q07 | answer | yes | 4.50 | 4.50 | +0.00 |
| q08 | refuse | no | 2.50 | 4.50 | +2.00 |
| q09 | answer | yes | 3.50 | 5.00 | +1.50 |
| q10 | answer | yes | 5.00 | 5.00 | +0.00 |
| q11 | refuse | no | 2.00 | 2.00 | +0.00 |
| q12 | answer | yes | 4.00 | 5.00 | +1.00 |
| q13 | answer | yes | 4.50 | 5.00 | +0.50 |
