"""
Routed (user-facing) answer quality for the CURRENT generator: stack-Pro vs stack-Flash
on the identical RRF+rerank retrieval. route_stack.py answered "does the router neutralise
the refuse regression" for Pro; this re-runs the same routed metric on the Flash answers so
the user-facing number reflects the live generator (Flash, lever 3).

For each cached answer we run the real router judge on the STORED context (no re-retrieval),
get its decision, and compute a routed user-facing overall:
  - decision = answer  -> the user sees the answer; score = the 3-judge panel overall.
  - decision = handoff -> a REFUSE question scored 4.0 (correct honest hand-off), an ANSWER
    question scored 2.0 (false hand-off — we withheld an answerable answer).
Convention read straight off the anchored rubric, identical to route_stack.py.

    ~/venvs/ambassy-poc/bin/python eval/route_flash.py
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from embed_index import get_token
import router

DIMS_J = ["gemini", "gpt", "claude"]
HANDOFF_REFUSE = 4.0
HANDOFF_ANSWER = 2.0


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
    pans = {j: load(f"judge_{j}{suffix}.jsonl") for j in DIMS_J}
    ids = set().union(*[set(p) for p in pans.values()]) if any(pans.values()) else set()
    return {qid: mean(pans[j].get(qid, {}).get("overall") for j in DIMS_J) for qid in ids}


def route_condition(answers_file, token):
    recs = [json.loads(l) for l in (HERE / answers_file).read_text(encoding="utf-8").splitlines() if l.strip()]
    out = {}
    for r in recs:
        if not r.get("answer"):
            continue
        try:
            v = router._judge(r["question"], r.get("retrieved_context", ""), r["answer"], token)
            answerable = bool(v.get("answerable"))
            confidence = int(v.get("confidence", 0))
        except Exception:
            answerable, confidence = False, 0
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
    conds = {"stack-pro": ("answers_stack.jsonl", "_stack"),
             "stack-flash": ("answers_flash.jsonl", "_flash")}
    routed, raw = {}, {}
    for name, (af, suf) in conds.items():
        routed[name] = route_condition(af, token)
        raw[name] = panel_overall(suf)

    ids = sorted(routed["stack-pro"])
    strata = {
        "ALL": ids,
        "in-corpus (answer)": [i for i in ids if routed["stack-pro"][i]["in_corpus"]],
        "out-of-corpus (refuse)": [i for i in ids if not routed["stack-pro"][i]["in_corpus"]],
    }

    def cond_overall(name, subset):
        return mean(routed_overall(routed[name][i], raw[name].get(i)) for i in subset)

    L = ["# Routed (user-facing) answer quality: stack-Pro vs stack-Flash · 2026-06-13", "",
         "Same RRF+rerank retrieval; generator gemini-2.5-pro vs gemini-2.5-flash (live). Routed "
         "overall = panel overall when the router ANSWERS, else a rubric hand-off score "
         "(refuse-handoff 4.0 correct; answer-handoff 2.0 false). Router judge on the stored context.",
         "", "## Routed overall by stratum (Pro → Flash)", "",
         "| stratum | raw overall (panel) | routed overall |", "|---|---|---|"]
    for sname, subset in strata.items():
        rp = cond_overall("stack-pro", subset)
        rf = cond_overall("stack-flash", subset)
        ro_p = mean(raw["stack-pro"].get(i) for i in subset)
        ro_f = mean(raw["stack-flash"].get(i) for i in subset)
        L.append(f"| {sname} | {fmt(ro_p)} → {fmt(ro_f)} ({fmt((ro_f or 0)-(ro_p or 0))}) | "
                 f"{fmt(rp)} → {fmt(rf)} ({fmt((rf or 0)-(rp or 0))}) |")

    L += ["", "## Per-question router decision + routed overall", "",
          "| id | exp | in-corpus | pro dec (conf) | flash dec (conf) | pro routed | flash routed |",
          "|---|---|---|---|---|---|---|"]
    for i in ids:
        p, fl = routed["stack-pro"][i], routed["stack-flash"][i]
        L.append(f"| {i} | {p['expected']} | {'yes' if p['in_corpus'] else 'no'} | "
                 f"{p['decision']} ({p['confidence']}) | {fl['decision']} ({fl['confidence']}) | "
                 f"{fmt(routed_overall(p, raw['stack-pro'].get(i)))} | "
                 f"{fmt(routed_overall(fl, raw['stack-flash'].get(i)))} |")

    report = "\n".join(L) + "\n"
    (HERE / "routed_flash.md").write_text(report, encoding="utf-8")
    print(report)
    print(f"[written] {HERE / 'routed_flash.md'}")


if __name__ == "__main__":
    main()
