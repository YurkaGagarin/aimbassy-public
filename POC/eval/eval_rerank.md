# Reranker (lever 2) — retrieval A/B on the enriched index · 2026-06-13

Conditions (same frozen DE rewrite): `enr+de` -> `enr+rrf` (lever 1) -> `enr+rrf+rerank` (Flash reranker over top-20 pool, kept top-5). Production functions reused; gold matched by parent §.

## 1. Statute recall (in-corpus law questions, n=11)

| condition | Hit@1 | Hit@3 | Hit@5 | Hit@10 | MRR |
|---|---|---|---|---|---|
| de | 0.45 | 0.73 | 0.73 | 0.73 | 0.57 |
| rrf | 0.45 | 0.64 | 0.64 | 0.73 | 0.54 |
| rrf+rerank | 0.45 | 0.64 | 0.64 | 0.82 | 0.58 |

### Per-question rank of first gold § (lower = better; '-' = not in top-60)

| id | de | rrf | rrf+rerank |
|---|---|---|---|
| q02 | 1 | 1 | 1 |
| q03 | 3 | 6 | 6 |
| q04 | 32 | 17 | 1 |
| q05 | 20 | 28 | 28 |
| q06 | 1 | 3 | 7 |
| q07 | 1 | 1 | 1 |
| q09 | 1 | 1 | 1 |
| q10 | - | 23 | 23 |
| q11 | 1 | 1 | 1 |
| q12 | 3 | 3 | 2 |
| q13 | 2 | 1 | 2 |

## 2. Case surfacing (any CASE-* in top-5)

| id | in_corpus | de | rrf | rrf+rerank |
|---|---|---|---|---|
| q01 | False | CASE-5, CASE-3 | CASE-5, CASE-3 | CASE-5, CASE-3 |
| q02 | True | - | - | - |
| q03 | True | - | - | - |
| q04 | True | - | - | - |
| q05 | True | - | - | CASE-5, CASE-3 |
| q06 | True | - | - | - |
| q07 | True | - | - | - |
| q08 | False | - | - | - |
| q09 | True | - | - | - |
| q10 | True | CASE-1, CASE-4 | CASE-1, CASE-4, CASE-2 | CASE-4, CASE-2, CASE-1 |
| q11 | True | - | CASE-2 | CASE-2, CASE-1 |
| q12 | True | - | - | - |
| q13 | True | - | - | - |
