"""
Day-4 exp 2: does the retrieval lever (cross-lingual query rewrite) actually lift
ANSWER quality, or only the retrieval numbers? Closes the loop on the Day-3 finding
that "the bottleneck is retrieval, not generation".

Same pipeline as the baseline (retrieve top-5 + gemini-2.5-pro grounded generation),
with ONE change: retrieval uses the FROZEN German rewrite (eval/query_rewrites.jsonl)
instead of the raw RU question. Generation still receives the original RU question, so
the answer to the user stays Russian — only WHAT we search with changes.

Rewrites are frozen (read from disk, not regenerated) so this A/B is reproducible and
not confounded by the rewrite non-determinism we measured in exp 1.

Reuses the baseline judge panel (judges.py: same anchored rubric, gemini + gpt) so the
scores are directly comparable to baseline_answers.md. Claude judges in-session from the
dumped judge_inputs_rewrite.jsonl.

    ~/venvs/ambassy-poc/bin/python eval/exp_answer_rewrite.py
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import prompts
from embed_index import get_token
from rag_core import retrieve, generate, TOP_K
from judges import judge_gemini, judge_gpt, build_user_block, RUBRIC

TESTSET = HERE / "testset.jsonl"
REWRITES = HERE / "query_rewrites.jsonl"
ANSWERS_OUT = HERE / "answers_rewrite.jsonl"


def generate_answers(rows, rewrites, token):
    out = []
    for r in rows:
        de = rewrites[r["id"]]["de"]                 # frozen German search query
        rec = {
            "id": r["id"], "difficulty": r["difficulty"], "in_corpus": r["in_corpus"],
            "expected_behavior": r["expected_behavior"], "question": r["question"],
            "rewrite_de": de,
            "gold_label": r["gold_label"], "gold_chunks": r["gold_chunks"],
            "reference_answer": r["reference_answer"],
        }
        try:
            hits = retrieve(de, country="AT", k=TOP_K, token=token)   # search WITH the DE rewrite
            rec["retrieved"] = [
                {"id": h["id"], "law": h["meta"].get("law_code", ""),
                 "paragraph": h["meta"].get("paragraph", ""), "distance": round(h["distance"], 3)}
                for h in hits
            ]
            rec["retrieved_context"] = prompts.format_context(hits)
            rec["answer"] = generate(r["question"], hits, country="AT", token=token)  # answer in RU
            rec["error"] = None
        except Exception as e:
            rec["retrieved"], rec["retrieved_context"] = rec.get("retrieved", []), ""
            rec["answer"], rec["error"] = None, f"{type(e).__name__}: {e}"
        out.append(rec)
        print(f"  gen {rec['id']}: {'OK' if rec['answer'] else 'ERROR ' + rec['error']}")
    return out


def main():
    rows = [json.loads(l) for l in TESTSET.read_text(encoding="utf-8").splitlines() if l.strip()]
    rewrites = {x["id"]: x for x in
                (json.loads(l) for l in REWRITES.read_text(encoding="utf-8").splitlines() if l.strip())}
    token = get_token()

    print("== generate (rewrite retrieval) ==")
    recs = generate_answers(rows, rewrites, token)
    with ANSWERS_OUT.open("w", encoding="utf-8") as f:
        for rec in recs:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"wrote {ANSWERS_OUT}")

    judgeable = [r for r in recs if r.get("answer")]

    # Claude judges in-session: dump the exact inputs (same rubric as baseline).
    with (HERE / "judge_inputs_rewrite.jsonl").open("w", encoding="utf-8") as f:
        for r in judgeable:
            f.write(json.dumps({"id": r["id"], "rubric": RUBRIC,
                                "input": build_user_block(r)}, ensure_ascii=False) + "\n")

    print("\n== judges ==")
    for vendor, fn in [("gemini", lambda r: judge_gemini(r, token)), ("gpt", judge_gpt)]:
        out = []
        for r in judgeable:
            try:
                score = fn(r)
                score["error"] = None
            except Exception as e:
                score = {"correctness": None, "grounding": None, "behavior": None,
                         "overall": None, "rationale": "", "error": f"{type(e).__name__}: {e}"}
            score["id"] = r["id"]
            out.append(score)
            print(f"  [{vendor}] {r['id']}: overall={score.get('overall')} {score['error'] or ''}")
        with (HERE / f"judge_{vendor}_rewrite.jsonl").open("w", encoding="utf-8") as f:
            for s in out:
                f.write(json.dumps(s, ensure_ascii=False) + "\n")
        print(f"  -> wrote judge_{vendor}_rewrite.jsonl\n")


if __name__ == "__main__":
    main()
