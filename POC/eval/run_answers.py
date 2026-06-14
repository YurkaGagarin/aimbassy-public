"""
Generate the system-under-test answers for the eval set (Day-3 baseline, part 2).

For each of the 13 questions we run the production pipeline (retrieve top-5 +
gemini-2.5-pro grounded generation) once and cache the result to answers.jsonl,
together with what was retrieved (so the judges can assess grounding). The judge
harness reads this cache — answers are generated once, judged many times.

    ~/venvs/ambassy-poc/bin/python eval/run_answers.py
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import prompts
from embed_index import get_token
from rag_core import retrieve, generate, TOP_K

TESTSET = HERE / "testset.jsonl"
OUT = HERE / "answers.jsonl"


def main():
    rows = [json.loads(l) for l in TESTSET.read_text(encoding="utf-8").splitlines() if l.strip()]
    token = get_token()

    out = []
    for r in rows:
        rec = {
            "id": r["id"], "difficulty": r["difficulty"], "in_corpus": r["in_corpus"],
            "expected_behavior": r["expected_behavior"], "question": r["question"],
            "gold_label": r["gold_label"], "gold_chunks": r["gold_chunks"],
            "reference_answer": r["reference_answer"],
        }
        try:
            hits = retrieve(r["question"], country="AT", k=TOP_K, token=token)
            rec["retrieved"] = [
                {"id": h["id"], "law": h["meta"].get("law_code", ""),
                 "paragraph": h["meta"].get("paragraph", ""), "distance": round(h["distance"], 3)}
                for h in hits
            ]
            rec["retrieved_context"] = prompts.format_context(hits)
            rec["answer"] = generate(r["question"], hits, country="AT", token=token)
            rec["error"] = None
        except Exception as e:                       # one failure must not lose the run
            rec["retrieved"], rec["retrieved_context"] = rec.get("retrieved", []), ""
            rec["answer"], rec["error"] = None, f"{type(e).__name__}: {e}"
        out.append(rec)
        print(f"  {rec['id']}: {'OK' if rec['answer'] else 'ERROR ' + rec['error']}")

    with OUT.open("w", encoding="utf-8") as f:
        for rec in out:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    ok = sum(1 for r in out if r["answer"])
    print(f"\nwrote {len(out)} answers ({ok} ok) -> {OUT}")


if __name__ == "__main__":
    main()
