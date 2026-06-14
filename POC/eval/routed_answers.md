# Routed (user-facing) answer quality: enr+de vs RRF+rerank stack · 2026-06-13

Does the router neutralise the raw refuse regression? Routed overall = panel overall when the router ANSWERS, else a rubric-derived hand-off score (refuse-handoff 4.0 = correct; answer-handoff 2.0 = false hand-off). Router judge run on the stored context.

## Routed overall by stratum (enr+de → stack)

| stratum | raw overall (panel) | routed overall |
|---|---|---|
| ALL | 4.05 → 3.90 (-0.15) | 3.62 → 3.87 (0.26) |
| in-corpus (answer) | 4.00 → 4.00 (0.00) | 3.58 → 4.00 (0.42) |
| out-of-corpus (refuse) | 4.33 → 3.33 (-1.00) | 3.83 → 3.17 (-0.67) |

## Per-question router decision + routed overall

| id | exp | in-corpus | enr+de dec (conf) | stack dec (conf) | enr+de routed | stack routed |
|---|---|---|---|---|---|---|
| q01 | refuse | no | handoff (4) | handoff (3) | 4.00 | 4.00 |
| q02 | answer | yes | answer (4) | answer (5) | 4.00 | 3.67 |
| q03 | answer | yes | answer (5) | answer (5) | 3.67 | 3.00 |
| q04 | answer | yes | answer (5) | answer (5) | 3.33 | 4.00 |
| q05 | answer | yes | handoff (3) | answer (5) | 2.00 | 4.00 |
| q06 | answer | yes | answer (5) | answer (5) | 3.33 | 3.33 |
| q07 | answer | yes | answer (5) | answer (5) | 4.00 | 4.33 |
| q08 | refuse | no | answer (5) | answer (5) | 3.67 | 2.33 |
| q09 | answer | yes | answer (5) | answer (5) | 4.67 | 3.67 |
| q10 | answer | yes | answer (5) | answer (5) | 4.33 | 4.33 |
| q11 | answer | yes | answer (5) | answer (5) | 3.33 | 4.33 |
| q12 | answer | yes | handoff (0) | answer (5) | 2.00 | 4.33 |
| q13 | answer | yes | answer (5) | answer (5) | 4.67 | 5.00 |
