"""
User-facing gate: does the ROUTER neutralise the refuse-question regression the raw
answer panel found (stack_answers.md: out-of-corpus overall 3.22 -> 2.67)?

The panel judged the raw generator output. In production the router runs AFTER generate
and hands off low-confidence / not-actionable answers to a human coordinator — it was
built precisely to turn the Day-4 confident-wrong refusals into honest hand-offs. So the
user never sees many of those weak answers. This script measures the routed outcome.

For each cached answer (enr+de and the RRF+rerank stack) we run the real router judge on
the STORED retrieved context (no re-retrieval), get its decision, and compute a routed
user-facing overall:
  - decision = answer  -> the user sees the answer; score = the existing 3-judge panel overall.
  - decision = handoff -> the user sees the honest hand-off text. By the rubric that is:
      * a REFUSE question  -> the correct outcome (honest "outside my sources" + coordinator).
        Scored 4.0: behavior-perfect, grounded (no claims), but gives no substance (not 5).
      * an ANSWER question -> a FALSE hand-off (we withheld an answerable answer). Scored 2.0.
This convention is read straight off the anchored rubric, so it matches what a judge would
give a templated hand-off; stated here so the number is transparent, not a black box.

    ~/venvs/ambassy-poc/bin/python eval/route_stack.py
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from embed_index import get_token
import router

DIMS_J = ["gemini", "gpt", "claude"]
HANDOFF_REFUSE = 4.0   # honest hand-off on a refuse question = correct, minimal-substance
HANDOFF_ANSWER = 2.0   # hand-off on an answerable question = false hand-off (withheld)


def load(name):
    p = HERE / name
    return {} if not p.exists() else {r["id"]: r for r in
            (json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip())}


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def fmt(x):
    return f"{x:.2f}" if isinstance(x, (int, float)) else "—"


def panel_overall(suffix):
    """Per-question 3-judge mean overall for a condition (from the cached judge files)."""
    pans = {j: load(f"judge_{j}{suffix}.jsonl") for j in DIMS_J}
    ids = set().union(*[set(p) for p in pans.values()]) if any(pans.values()) else set()
    return {qid: mean(pans[j].get(qid, {}).get("overall") for j in DIMS_J) for qid in ids}


def route_condition(answers_file, token):
    """Run the router judge on each cached answer via its stored context; return decisions."""
    recs = [json.loads(l) for l in (HERE / answers_file).read_text(encoding="utf-8").splitlines() if l.strip()]
    out = {}
    for r in recs:
        if not r.get("answer"):
            continue
        try:
            v = router._judge(r["question"], r.get("retrieved_context", ""), r["answer"], token)
            answerable = bool(v.get("answerable"))
            confidence = int(v.get("confidence", 0))
        except Exception as e:
            answerable, confidence = False, 0   # fail-safe = handoff, as in router.route
        handoff = (not answerable) or confidence <= router.CONFIDENCE_THRESHOLD
        out[r["id"]] = {"decision": "handoff" if handoff else "answer",
                        "confidence": confidence, "in_corpus": r["in_corpus"],
                        "expected": r["expected_behavior"]}
    return out


def routed_overall(decision_rec, raw_overall):
    if decision_rec["decision"] == "answer":
        return raw_overall
    return HANDOFF_REFUSE if decision_rec["expected"] == "refuse" else HANDOFF_ANSWER


def main():
    token = get_token()
    conds = {"enr+de": ("answers_enriched.jsonl", "_enriched"),
             "stack":  ("answers_stack.jsonl", "_stack")}
    routed, raw = {}, {}
    for name, (af, suf) in conds.items():
        routed[name] = route_condition(af, token)
        raw[name] = panel_overall(suf)

    ids = sorted(routed["enr+de"])
    strata = {
        "ALL": ids,
        "in-corpus (answer)": [i for i in ids if routed["enr+de"][i]["in_corpus"]],
        "out-of-corpus (refuse)": [i for i in ids if not routed["enr+de"][i]["in_corpus"]],
    }

    def cond_overall(name, subset):
        return mean(routed_overall(routed[name][i], raw[name].get(i)) for i in subset)

    L = ["# Routed (user-facing) answer quality: enr+de vs RRF+rerank stack · 2026-06-13", "",
         "Does the router neutralise the raw refuse regression? Routed overall = panel overall "
         "when the router ANSWERS, else a rubric-derived hand-off score (refuse-handoff 4.0 = "
         "correct; answer-handoff 2.0 = false hand-off). Router judge run on the stored context.",
         "", "## Routed overall by stratum (enr+de → stack)", "",
         "| stratum | raw overall (panel) | routed overall |", "|---|---|---|"]
    raw_strat = {"enr+de": {}, "stack": {}}
    for sname, subset in strata.items():
        rd = cond_overall("enr+de", subset)
        rs = cond_overall("stack", subset)
        # raw (no router) for reference
        ro_de = mean(raw["enr+de"].get(i) for i in subset)
        ro_st = mean(raw["stack"].get(i) for i in subset)
        L.append(f"| {sname} | {fmt(ro_de)} → {fmt(ro_st)} ({fmt((ro_st or 0)-(ro_de or 0))}) | "
                 f"{fmt(rd)} → {fmt(rs)} ({fmt((rs or 0)-(rd or 0))}) |")

    L += ["", "## Per-question router decision + routed overall", "",
          "| id | exp | in-corpus | enr+de dec (conf) | stack dec (conf) | enr+de routed | stack routed |",
          "|---|---|---|---|---|---|---|"]
    for i in ids:
        de, st = routed["enr+de"][i], routed["stack"][i]
        L.append(f"| {i} | {de['expected']} | {'yes' if de['in_corpus'] else 'no'} | "
                 f"{de['decision']} ({de['confidence']}) | {st['decision']} ({st['confidence']}) | "
                 f"{fmt(routed_overall(de, raw['enr+de'].get(i)))} | "
                 f"{fmt(routed_overall(st, raw['stack'].get(i)))} |")

    report = "\n".join(L) + "\n"
    (HERE / "routed_answers.md").write_text(report, encoding="utf-8")
    print(report)
    print(f"[written] {HERE / 'routed_answers.md'}")


if __name__ == "__main__":
    main()
