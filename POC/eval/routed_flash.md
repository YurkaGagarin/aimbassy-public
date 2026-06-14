# Routed (user-facing) answer quality: stack-Pro vs stack-Flash · 2026-06-13

Same RRF+rerank retrieval; generator gemini-2.5-pro vs gemini-2.5-flash (live). Routed overall = panel overall when the router ANSWERS, else a rubric hand-off score (refuse-handoff 4.0 correct; answer-handoff 2.0 false). Router judge on the stored context.

## Routed overall by stratum (Pro → Flash)

| stratum | raw overall (panel) | routed overall |
|---|---|---|
| ALL | 3.90 → 3.85 (-0.05) | 3.87 → 3.82 (-0.05) |
| in-corpus (answer) | 4.00 → 3.97 (-0.03) | 4.00 → 3.97 (-0.03) |
| out-of-corpus (refuse) | 3.33 → 3.17 (-0.17) | 3.17 → 3.00 (-0.17) |

## Per-question router decision + routed overall

| id | exp | in-corpus | pro dec (conf) | flash dec (conf) | pro routed | flash routed |
|---|---|---|---|---|---|---|
| q01 | refuse | no | handoff (3) | handoff (4) | 4.00 | 4.00 |
| q02 | answer | yes | answer (5) | answer (4) | 3.67 | 4.00 |
| q03 | answer | yes | answer (5) | answer (5) | 3.00 | 3.33 |
| q04 | answer | yes | answer (5) | answer (5) | 4.00 | 4.00 |
| q05 | answer | yes | answer (5) | answer (5) | 4.00 | 3.67 |
| q06 | answer | yes | answer (5) | answer (5) | 3.33 | 3.00 |
| q07 | answer | yes | answer (5) | answer (5) | 4.33 | 4.00 |
| q08 | refuse | no | answer (5) | answer (5) | 2.33 | 2.00 |
| q09 | answer | yes | answer (5) | answer (4) | 3.67 | 3.33 |
| q10 | answer | yes | answer (5) | answer (5) | 4.33 | 4.33 |
| q11 | answer | yes | answer (5) | answer (5) | 4.33 | 4.33 |
| q12 | answer | yes | answer (5) | answer (5) | 4.33 | 4.67 |
| q13 | answer | yes | answer (5) | answer (5) | 5.00 | 5.00 |
