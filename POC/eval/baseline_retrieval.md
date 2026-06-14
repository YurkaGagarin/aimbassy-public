# Baseline — Retrieval (SICRT) · 2026-06-10

Corpus: 442 chunks · retriever: gemini-embedding-001 (768d, cosine) · prod top-k=5.
In-corpus questions only; out-of-corpus (refuse) judged separately.

## Summary (stratified)

| stratum | n | Hit@1 | Hit@3 | Hit@5 | Hit@10 | MRR | Cov@5 |
|---|---|---|---|---|---|---|---|
| ALL in-corpus | 7 | 0.14 | 0.14 | 0.14 | 0.43 | 0.21 | 0.14 |
| easy | 5 | 0.20 | 0.20 | 0.20 | 0.20 | 0.23 | 0.20 |
| difficult | 2 | 0.00 | 0.00 | 0.00 | 1.00 | 0.15 | 0.00 |

## Per question (in-corpus)

| id | diff | primary gold | rank | hit@5 | note |
|---|---|---|---|---|---|
| q03 | easy | AuslBG-4 | 12 | NO |  |
| q04 | easy | AsylG-13,AsylG-51 | 21 | NO |  |
| q07 | difficult | AsylG-10 | 6 | NO | lenient rank 6 |
| q09 | easy | FPG-88 | 1 | yes |  |
| q10 | easy | NAG-19 | 71 | NO |  |
| q12 | easy | StbG-20 | 34 | NO |  |
| q13 | difficult | NAG-DV-7,FPG-16 | 8 | NO |  |

## Out-of-corpus (expected: honest refusal — scored by judges)

- q01 (difficult): top-1 retrieved = `CASE-1` (no gold expected)
- q02 (easy): top-1 retrieved = `AsylG-27a` (no gold expected)
- q05 (difficult): top-1 retrieved = `AsylG-3` (no gold expected)
- q06 (difficult): top-1 retrieved = `CASE-2` (no gold expected)
- q08 (difficult): top-1 retrieved = `AsylG-4a` (no gold expected)
- q11 (difficult): top-1 retrieved = `CASE-2` (no gold expected)
