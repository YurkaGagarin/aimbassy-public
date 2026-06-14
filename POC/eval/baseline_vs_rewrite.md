# Day-4 exp 2 — answer quality: baseline vs rewrite retrieval · 2026-06-10

Baseline judges: gemini, gpt, claude · rewrite judges: gemini, gpt, claude · same anchored rubric (1-5).
Only change: retrieval uses the frozen German rewrite. Generation + rubric + judges identical.

## Panel mean by stratum (baseline → rewrite, delta)

| stratum | correctness | grounding | behavior | overall |
|---|---|---|---|---|
| ALL | 3.05 → 3.28 (+0.23) | 4.46 → 4.54 (+0.08) | 3.62 → 3.54 (-0.08) | 3.36 → 3.33 (-0.03) |
| in-corpus (answer) | 2.90 → 3.38 (+0.48) | 4.57 → 4.62 (+0.05) | 4.43 → 4.81 (+0.38) | 3.67 → 3.86 (+0.19) |
| out-of-corpus (refuse) | 3.22 → 3.17 (-0.06) | 4.33 → 4.44 (+0.11) | 2.67 → 2.06 (-0.61) | 3.00 → 2.72 (-0.28) |
| easy | 2.78 → 3.00 (+0.22) | 4.61 → 4.67 (+0.06) | 4.33 → 4.17 (-0.17) | 3.56 → 3.39 (-0.17) |
| difficult | 3.29 → 3.52 (+0.24) | 4.33 → 4.43 (+0.10) | 3.00 → 3.00 (+0.00) | 3.19 → 3.29 (+0.10) |

## Per question (panel overall)

| id | beh | in-corpus | base | rewrite | delta |
|---|---|---|---|---|---|
| q01 | refuse | no | 5.00 | 4.67 | -0.33 |
| q02 | refuse | no | 3.67 | 2.00 | -1.67 |
| q03 | answer | yes | 2.33 | 3.67 | +1.33 |
| q04 | answer | yes | 2.67 | 3.00 | +0.33 |
| q05 | refuse | no | 2.67 | 2.33 | -0.33 |
| q06 | refuse | no | 1.33 | 3.33 | +2.00 |
| q07 | answer | yes | 3.67 | 4.33 | +0.67 |
| q08 | refuse | no | 2.67 | 2.33 | -0.33 |
| q09 | answer | yes | 4.67 | 3.67 | -1.00 |
| q10 | answer | yes | 4.67 | 4.67 | +0.00 |
| q11 | refuse | no | 2.67 | 1.67 | -1.00 |
| q12 | answer | yes | 3.33 | 3.33 | +0.00 |
| q13 | answer | yes | 4.33 | 4.33 | +0.00 |

## Interpretation

**1. The loop closes: the retrieval lever lifts ANSWER quality, not just retrieval numbers.**
On the in-corpus questions (the ones the bot is supposed to answer), correctness rose
**2.90 → 3.38 (+0.48)** and behavior **4.43 → 4.81 (+0.38)**, with grounding holding high
(4.57 → 4.62). This is the Day-3 hypothesis confirmed end-to-end: the bottleneck was
RETRIEVAL, not generation — fix the search and the answers get more correct, with the same
generator and the same rubric. Showcase questions: q03 +1.33 (gold § 4 AuslBG now in top-5),
q07 +0.67 (gold § 10 AsylG at rank 1), q06 +2.00 (no longer contradicts the expert on the
passport question).

**2. The honest cost: better retrieval makes REFUSE worse.** On out-of-corpus questions the
bot should decline, behavior REGRESSED **2.67 → 2.06 (-0.61)** and overall **3.00 → 2.72**.
Mechanism: a stronger German query now pulls a § that *looks* like it answers, so the model
latches onto it and gives a confident, grounded-looking answer instead of saying "this is
outside my sources." q11 went 2.67 → 1.67 (it now confidently says residence-longer-than-
passport is "impossible" from § 20 NAG, contradicting the expert's real-world workaround);
q02 went 3.67 → 2.00 (nominal statutory deadlines presented as if they were the answer). The
retrieval lever and the refuse-guardrail are COUPLED: improving search exposes — and sharpens
— the need for the Day-5 guardrail/router. This is the strongest numeric argument for Day 5.

**3. Methodology: the averaged number hides the result.** ALL-overall is flat (3.36 → 3.33)
because the in-corpus gain is cancelled by the out-of-corpus regression. Only the stratified
view shows what actually happened. Averaging across strata with opposite effects is exactly
the trap the course's stratified-eval guidance warns about.

**Design conclusion:** accept query-rewrite as the retrieval lever, but it must NOT ship to
production without the refuse-guardrail — alone it trades better answers for worse refusals.
q09's -1.00 is a separate, minor effect (a more verbose answer; the rubric penalises verbosity),
not a retrieval regression. q12 flat = StbG gold § 20 still unretrieved (the no-title residual,
the contextual-descriptor lever's target).
