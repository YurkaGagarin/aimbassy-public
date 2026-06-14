# Retrieval-stack answer quality: enr+de (live) vs enr+rrf+rerank · 2026-06-13

Panel = judges present for BOTH conditions: gemini, gpt, claude. Same anchored rubric (1-5). Only change vs live: retrieval = RRF(RU+DE) fusion + Flash reranker (same enriched index, same frozen German rewrite). Generator (gemini-2.5-pro) + prompt + rubric identical.

## Panel mean by stratum (enr+de → enr+rrf+rerank, delta)

| stratum | correctness | grounding | behavior | overall |
|---|---|---|---|---|
| ALL | 3.79 → 3.72 (-0.08) | 4.64 → 4.44 (-0.21) | 4.56 → 4.62 (+0.05) | 4.05 → 3.90 (-0.15) |
| in-corpus (answer) | 3.67 → 3.70 (+0.03) | 4.67 → 4.55 (-0.12) | 4.61 → 4.85 (+0.24) | 4.00 → 4.00 (+0.00) |
| out-of-corpus (refuse) | 4.50 → 3.83 (-0.67) | 4.50 → 3.83 (-0.67) | 4.33 → 3.33 (-1.00) | 4.33 → 3.33 (-1.00) |
| easy | 3.67 → 3.61 (-0.06) | 4.78 → 4.67 (-0.11) | 4.56 → 4.83 (+0.28) | 4.11 → 3.83 (-0.28) |
| difficult | 3.90 → 3.81 (-0.10) | 4.52 → 4.24 (-0.29) | 4.57 → 4.43 (-0.14) | 4.00 → 3.95 (-0.05) |

## Per question (panel overall)

| id | beh | in-corpus | enr+de | stack | delta |
|---|---|---|---|---|---|
| q01 | refuse | no | 5.00 | 4.33 | -0.67 |
| q02 | answer | yes | 4.00 | 3.67 | -0.33 |
| q03 | answer | yes | 3.67 | 3.00 | -0.67 |
| q04 | answer | yes | 3.33 | 4.00 | +0.67 |
| q05 | answer | yes | 4.00 | 4.00 | +0.00 |
| q06 | answer | yes | 3.33 | 3.33 | +0.00 |
| q07 | answer | yes | 4.00 | 4.33 | +0.33 |
| q08 | refuse | no | 3.67 | 2.33 | -1.33 |
| q09 | answer | yes | 4.67 | 3.67 | -1.00 |
| q10 | answer | yes | 4.33 | 4.33 | +0.00 |
| q11 | answer | yes | 3.33 | 4.33 | +1.00 |
| q12 | answer | yes | 4.67 | 4.33 | -0.33 |
| q13 | answer | yes | 4.67 | 5.00 | +0.33 |
