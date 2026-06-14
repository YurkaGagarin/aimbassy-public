# RRF(RU+DE) — retrieval A/B on the enriched index · 2026-06-13

Conditions on aimbassy_corpus_enriched: `enr+de` (frozen DE rewrite only = current live path) vs `enr+rrf` (RRF fusion of raw RU question + frozen DE rewrite, c=60). Gold matched by parent §.

## 1. Statute recall (in-corpus law questions, n=11)

| condition | Hit@1 | Hit@3 | Hit@5 | Hit@10 | MRR |
|---|---|---|---|---|---|
| de | 0.45 | 0.73 | 0.73 | 0.73 | 0.57 |
| rrf | 0.45 | 0.64 | 0.64 | 0.73 | 0.54 |

### Per-question rank of first gold § (lower = better; '-' = not in top-100)

| id | de | rrf |
|---|---|---|
| q02 | 1 | 1 |
| q03 | 3 | 6 |
| q04 | 32 | 14 |
| q05 | 20 | 38 |
| q06 | 1 | 3 |
| q07 | 1 | 1 |
| q09 | 1 | 1 |
| q10 | 71 | 33 |
| q11 | 1 | 1 |
| q12 | 3 | 3 |
| q13 | 2 | 1 |

## 2. Case surfacing (any CASE-* chunk in top-5)

Questions with >=1 case in top-5: **de=2/13 -> rrf=3/13**.

| id | in_corpus | de | rrf |
|---|---|---|---|
| q01 | False | CASE-5, CASE-3 | CASE-5, CASE-3 |
| q02 | True | - | - |
| q03 | True | - | - |
| q04 | True | - | - |
| q05 | True | - | - |
| q06 | True | - | - |
| q07 | True | - | - |
| q08 | False | - | - |
| q09 | True | - | - |
| q10 | True | CASE-1, CASE-4 | CASE-1, CASE-4, CASE-2 |
| q11 | True | - | CASE-2 |
| q12 | True | - | - |
| q13 | True | - | - |
