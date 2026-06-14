# Lever 3 answer quality: Pro stack vs Flash stack (same RRF+rerank) · 2026-06-13

Panel = gemini, gpt, claude. Same anchored rubric (1-5). Only change: generator gemini-2.5-pro → gemini-2.5-flash on identical retrieved context. Strata post-relabel (11 answer / 2 refuse). Generate latency: Pro ~23.8s → Flash ~12.5s (flash_latency.md).

## Panel mean by stratum (Pro → Flash, delta)

| stratum | correctness | grounding | behavior | overall |
|---|---|---|---|---|
| ALL | 3.72 → 3.59 (-0.13) | 4.44 → 4.62 (+0.18) | 4.62 → 4.49 (-0.13) | 3.90 → 3.85 (-0.05) |
| in-corpus (answer) | 3.70 → 3.61 (-0.09) | 4.55 → 4.76 (+0.21) | 4.85 → 4.76 (-0.09) | 4.00 → 3.97 (-0.03) |
| out-of-corpus (refuse) | 3.83 → 3.50 (-0.33) | 3.83 → 3.83 (+0.00) | 3.33 → 3.00 (-0.33) | 3.33 → 3.17 (-0.17) |
| easy | 3.61 → 3.50 (-0.11) | 4.67 → 4.78 (+0.11) | 4.83 → 4.78 (-0.06) | 3.83 → 3.94 (+0.11) |
| difficult | 3.81 → 3.67 (-0.14) | 4.24 → 4.48 (+0.24) | 4.43 → 4.24 (-0.19) | 3.95 → 3.76 (-0.19) |

## Per question (panel overall)

| id | beh | in-corpus | Pro stack | Flash stack | delta |
|---|---|---|---|---|---|
| q01 | refuse | no | 4.33 | 4.33 | +0.00 |
| q02 | answer | yes | 3.67 | 4.00 | +0.33 |
| q03 | answer | yes | 3.00 | 3.33 | +0.33 |
| q04 | answer | yes | 4.00 | 4.00 | +0.00 |
| q05 | answer | yes | 4.00 | 3.67 | -0.33 |
| q06 | answer | yes | 3.33 | 3.00 | -0.33 |
| q07 | answer | yes | 4.33 | 4.00 | -0.33 |
| q08 | refuse | no | 2.33 | 2.00 | -0.33 |
| q09 | answer | yes | 3.67 | 3.33 | -0.33 |
| q10 | answer | yes | 4.33 | 4.33 | +0.00 |
| q11 | answer | yes | 4.33 | 4.33 | +0.00 |
| q12 | answer | yes | 4.33 | 4.67 | +0.33 |
| q13 | answer | yes | 5.00 | 5.00 | +0.00 |
