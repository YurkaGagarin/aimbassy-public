# Day-5.4 router eval — v2 (grounded + actionable rubric) · 2026-06-12

13 rewrite-pipeline answers. Gold: in-corpus -> answer, out-of-corpus -> handoff.
Hand-off if not answerable OR confidence <= 2.

- in-corpus answered (kept, good): **7/7**
- out-of-corpus handed off (caught, good): **2/6**
- vs v1 (groundedness-only rubric, `router_eval_v1.md`): caught **1/6 -> 2/6** (gained q05), in-corpus 7/7 unchanged.
- stable across 3 runs despite the thinking-model non-determinism (q01/q05 -> handoff, q02/q06/q08/q11 -> answer every run).
- still shipped: q02/q11 are genuinely harmful but structurally invisible to the router — the answer is a grounded clean "no" the judge rightly rates as a valid legal answer; only adding НП practice notes to the corpus closes them, not a sharper judge. q06/q08 answers were adequate per the Day-4 panel.

| id | in_corpus | gold | router | conf | correct |
|---|---|---|---|---|---|
| q01 | no | handoff | handoff | 2 | yes |
| q02 | no | handoff | answer | 5 | NO |
| q03 | yes | answer | answer | 5 | yes |
| q04 | yes | answer | answer | 5 | yes |
| q05 | no | handoff | handoff | 2 | yes |
| q06 | no | handoff | answer | 5 | NO |
| q07 | yes | answer | answer | 5 | yes |
| q08 | no | handoff | answer | 5 | NO |
| q09 | yes | answer | answer | 5 | yes |
| q10 | yes | answer | answer | 5 | yes |
| q11 | no | handoff | answer | 5 | NO |
| q12 | yes | answer | answer | 4 | yes |
| q13 | yes | answer | answer | 5 | yes |
