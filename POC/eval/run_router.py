"""
Day-5.4 router eval. Runs the router judge over the 13 real answers produced with the
rewrite-retrieval pipeline (eval/answers_rewrite.jsonl) and checks whether it sends the
right ones to a human hand-off.

Gold: in_corpus questions SHOULD be answered; out-of-corpus questions SHOULD be handed
off (this is the -0.61 refusal gap from Day 4 that the router is meant to close).

Reads answers_rewrite.jsonl locally (gitignored — carries case text). This report writes
ONLY ids / decisions / numbers, no case text, so it is safe to commit.

    ~/venvs/ambassy-poc/bin/python eval/run_router.py
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from embed_index import get_token
from router import _judge, CONFIDENCE_THRESHOLD

ANSWERS = HERE / "answers_rewrite.jsonl"


def main():
    rows = [json.loads(l) for l in ANSWERS.read_text(encoding="utf-8").splitlines() if l.strip()]
    token = get_token()

    results = []
    for r in rows:
        if not r.get("answer"):
            continue
        try:
            v = _judge(r["question"], r.get("retrieved_context", ""), r["answer"], token)
            answerable, confidence = bool(v.get("answerable")), int(v.get("confidence", 0))
            reason = v.get("reason", "")
        except Exception as e:
            answerable, confidence, reason = False, 0, f"error:{type(e).__name__}"
        decision = "handoff" if (not answerable or confidence <= CONFIDENCE_THRESHOLD) else "answer"
        gold = "answer" if r["in_corpus"] else "handoff"
        results.append({"id": r["id"], "in_corpus": r["in_corpus"], "gold": gold,
                        "decision": decision, "answerable": answerable,
                        "confidence": confidence, "correct": decision == gold, "reason": reason})
        print(f"  {r['id']}: gold={gold:7} decision={decision:7} conf={confidence} ok={decision==gold}")

    inc = [r for r in results if r["in_corpus"]]
    out = [r for r in results if not r["in_corpus"]]
    ans_kept = sum(1 for r in inc if r["decision"] == "answer")
    handed = sum(1 for r in out if r["decision"] == "handoff")

    L = ["# Day-5.4 router eval — v2 (grounded + actionable rubric) · 2026-06-12", "",
         f"13 rewrite-pipeline answers. Gold: in-corpus -> answer, out-of-corpus -> handoff.",
         f"Hand-off if not answerable OR confidence <= {CONFIDENCE_THRESHOLD}.", "",
         f"- in-corpus answered (kept, good): **{ans_kept}/{len(inc)}**",
         f"- out-of-corpus handed off (caught, good): **{handed}/{len(out)}**", "",
         "| id | in_corpus | gold | router | conf | correct |", "|---|---|---|---|---|---|"]
    for r in results:
        L.append(f"| {r['id']} | {'yes' if r['in_corpus'] else 'no'} | {r['gold']} | "
                 f"{r['decision']} | {r['confidence']} | {'yes' if r['correct'] else 'NO'} |")
    report = "\n".join(L) + "\n"
    (HERE / "router_eval.md").write_text(report, encoding="utf-8")
    print("\n" + report)
    print(f"[written] {HERE / 'router_eval.md'}")


if __name__ == "__main__":
    main()
