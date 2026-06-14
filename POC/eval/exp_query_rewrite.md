# Day-4 exp 1 — cross-lingual query rewrite (RU → formal DE) · 2026-06-10

Lever: rewrite the lay Russian question into a short FORMAL German legal search query
(gemini-2.5-flash, key-free Vertex path), embed THAT for retrieval. The authoritative
German corpus is never touched — only what we search WITH changes, so cited §§ stay exact.

In-corpus questions: 7. Retrieval: gemini-embedding-001, prod top-k=5. SICRT gold = volunteers' § → chunk_id.

## Stabilized before / after (5 runs)

The rewrite is NOT deterministic (see note below), so a single run is not a measurement.
Numbers below are the mean over 5 independent rewrite+retrieve runs, with spread.

| metric | baseline RU | rewrite DE (mean) | min | max | stdev |
|---|---|---|---|---|---|
| Hit@5 | 0.14 | **0.57** | 0.43 | 0.71 | 0.09 |
| MRR   | 0.21 | **0.56** | 0.46 | 0.63 | 0.07 |

Effect dwarfs the noise: even the WORST run (Hit@5 0.43) is 3× baseline; best is 5×.
The cross-lingual gap is confirmed as the dominant cause of the weak baseline retrieval.

## Per-question signal (one representative run — exact ranks vary run-to-run)

| id | diff | gold | rank RU | rank DE | note |
|---|---|---|---|---|---|
| q03 | easy | AuslBG-4 | 12 | 5 | retriever still also likes 20b (arguably more relevant) |
| q04 | easy | AsylG-13,51 | 21 | 26→1* | showcase across runs: cross-lingual fix lands gold near rank 1 |
| q07 | difficult | AsylG-10 | 6 | 1 | rises to top with DE query |
| q09 | easy | FPG-88 | 1 | 1 | already strong; rewrite holds it |
| q10 | easy | NAG-19 | 71 | >100 | REGRESSION — buried sub-clause; rewrite doesn't help, residual gap |
| q12 | easy | StbG-20 | 34 | 19 | StbG (no per-§ titles) benefits from legalese query |
| q13 | difficult | NAG-DV-7,FPG-16 | 8 | 1 | the law we just ingested; rises to top with DE |

\* q04's DE rank swings (1 in some runs, 26 in others) — exactly the non-determinism quantified above.

q10 is the honest miss: the answer is a buried sub-clause inside a long §; neither RU nor DE
query surfaces it in top-5. This is the residual that a contextual-descriptor / reranker lever
(Day-4 candidate 2) would target, not query rewrite.

## Methodological note — temp=0 ≠ deterministic on a thinking model

query_rewrite.py sets `temperature: 0`, yet the German wording (and thus the ranks) changes
run-to-run. gemini-2.5-flash is a "thinking" model; the internal reasoning trace is not pinned
by temperature, so the final search query drifts. Implication for production: pin/cache the
rewrite per question, OR generate N rewrites and RRF-fuse them, to remove variance from the
serving path. The *lever* is validated; the *serving* needs a determinism wrapper.

## RRF fusion (original RU + rewrite DE) — rejected

Fusing the original RU retrieval with the DE retrieval gave LOWER Hit@5 than DE-alone (0.43 vs
0.57 in the run above): the RU query is too weak and dilutes the strong DE signal. So
rewrite-DE-only > fused > original-RU. Multi-query fusion is still useful — but fuse several DE
rewrites, not RU+DE.
