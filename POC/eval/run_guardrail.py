"""
Day-5 guardrail mini-eval. Runs the input guardrail (guardrail.guard) over a labeled
set of synthetic messages and scores each of its three gates as a binary classifier,
which is where a confusion matrix and Accuracy/Precision/Recall/F1 actually belong
(course canon: guardrail = да/нет classification, deck 03).

Positive class per gate (the "risk" we must catch — so Recall is the safety metric):
  topic      positive = OFF-topic  (we must reject non-immigration messages)
  injection  positive = injection   (we must catch prompt-injection)
  pii        positive = PII present (we must scrub before anything is stored)

All inputs are fictional (no client data). Writes eval/guardrail_eval.md and
eval/guardrail_predictions.jsonl (synthetic, safe to commit).

    ~/venvs/ambassy-poc/bin/python eval/run_guardrail.py
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from embed_index import get_token
from guardrail import guard

TESTSET = HERE / "guardrail_testset.jsonl"


def confusion(rows, gold_key, pred_key):
    """Binary confusion with positive = True on both keys. Returns counts + metrics."""
    tp = fp = fn = tn = 0
    wrong = []
    for r in rows:
        g, p = bool(r[gold_key]), bool(r[pred_key])
        if g and p:
            tp += 1
        elif not g and p:
            fp += 1; wrong.append((r["id"], "FP"))
        elif g and not p:
            fn += 1; wrong.append((r["id"], "FN"))
        else:
            tn += 1
    n = tp + fp + fn + tn
    acc = (tp + tn) / n if n else 0.0
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "acc": acc, "prec": prec,
            "rec": rec, "f1": f1, "wrong": wrong}


def main():
    rows = [json.loads(l) for l in TESTSET.read_text(encoding="utf-8").splitlines() if l.strip()]
    token = get_token()

    preds = []
    for r in rows:
        v = guard(r["text"], token)
        preds.append({
            "id": r["id"],
            "gold_on_topic": r["on_topic"], "gold_injection": r["injection"], "gold_pii": r["pii"],
            "pred_off_topic": not v["on_topic"], "pred_injection": v["injection"],
            "pred_pii": v["pii_found"], "action": v["action"],
            "gold_off_topic": not r["on_topic"],
            "scrubbed": v["scrubbed"], "pii_types": v["pii_types"],
        })
        print(f"  {r['id']}: action={v['action']} on_topic={v['on_topic']} "
              f"inj={v['injection']} pii={v['pii_found']}")

    (HERE / "guardrail_predictions.jsonl").write_text(
        "\n".join(json.dumps(p, ensure_ascii=False) for p in preds) + "\n", encoding="utf-8")

    gates = [
        ("topic (positive = OFF-topic)", "gold_off_topic", "pred_off_topic"),
        ("injection (positive = injection)", "gold_injection", "pred_injection"),
        ("pii (positive = PII present)", "gold_pii", "pred_pii"),
    ]
    L = ["# Day-5 guardrail mini-eval (confusion matrix) · 2026-06-10", "",
         f"Labeled synthetic messages: {len(rows)}. Gate = binary classifier; positive = the risk to catch.",
         "Recall is the safety-critical metric (a missed risk is worse than a false alarm).", ""]
    for title, gk, pk in gates:
        c = confusion(preds, gk, pk)
        L += [f"## {title}", "",
              "| | pred + | pred - |", "|---|---|---|",
              f"| **actual +** | TP {c['tp']} | FN {c['fn']} |",
              f"| **actual -** | FP {c['fp']} | TN {c['tn']} |", "",
              f"Accuracy {c['acc']:.2f} · Precision {c['prec']:.2f} · Recall {c['rec']:.2f} · F1 {c['f1']:.2f}",
              (f"Misclassified: " + ", ".join(f"{i}({t})" for i, t in c["wrong"]) if c["wrong"]
               else "Misclassified: none"), ""]
    report = "\n".join(L) + "\n"
    (HERE / "guardrail_eval.md").write_text(report, encoding="utf-8")
    print("\n" + report)
    print(f"[written] {HERE / 'guardrail_eval.md'}")


if __name__ == "__main__":
    main()
