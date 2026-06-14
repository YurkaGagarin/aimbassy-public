"""
Answer-quality panel for the FULL retrieval stack (lever 1 RRF + lever 2 reranker),
to measure whether the retrieval gains translate into better ANSWERS — the Day-4 lesson
was that better retrieval can hurt answers (the -0.61 refusal regression).

Baseline = enr+de (current live index + frozen German rewrite), whose panel already
exists as judge_*_enriched.jsonl. Candidate = enr+rrf+rerank: same enriched index and
same frozen German rewrite, but retrieval = RRF(RU+DE) fusion then Flash rerank, kept
top-5. Same generator (gemini-2.5-pro), same rubric, same judges -> directly comparable.

FAITHFUL to production: uses the real rag_core.retrieve_rrf + rerank.rerank path; the only
deliberate difference from the live bot is the FROZEN German rewrite (the live one is
non-deterministic), which isolates the levers from rewrite jitter. Generation still gets
the original RU question, so the answer stays Russian and the cited § stays exact.

Generation only (judging is a separate step, to stay under the shell timeout):
    ~/venvs/ambassy-poc/bin/python eval/exp_answer_stack.py
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import prompts
import rag_core
import rerank
from embed_index import get_token
from rag_core import generate, retrieve_rrf, TOP_K
from judges import build_user_block, RUBRIC

TESTSET = HERE / "testset.jsonl"
REWRITES = HERE / "query_rewrites.jsonl"
ANSWERS_OUT = HERE / "answers_stack.jsonl"
INPUTS_OUT = HERE / "judge_inputs_stack.jsonl"


def stack_retrieve(ru, de, token):
    """Production retrieval stack: RRF(RU+DE) fusion over a deep pool, then Flash rerank,
    kept top-5. Same calls graph.py makes, with the frozen DE rewrite for reproducibility."""
    pool = retrieve_rrf(ru, de, country="AT", k=rerank.RERANK_POOL, token=token)
    return rerank.rerank(ru, pool, token=token, top_k=TOP_K)


def main():
    rows = [json.loads(l) for l in TESTSET.read_text(encoding="utf-8").splitlines() if l.strip()]
    rewrites = {x["id"]: x for x in
                (json.loads(l) for l in REWRITES.read_text(encoding="utf-8").splitlines() if l.strip())}
    token = get_token()
    print(f"serving collection: {rag_core.SERVING_COLLECTION}")
    print("== generate (RRF + rerank, gemini-2.5-pro) ==")

    recs = []
    for r in rows:
        ru, de = r["question"], rewrites[r["id"]]["de"]
        rec = {
            "id": r["id"], "difficulty": r["difficulty"], "in_corpus": r["in_corpus"],
            "expected_behavior": r["expected_behavior"], "question": ru, "rewrite_de": de,
            "gold_label": r["gold_label"], "gold_chunks": r["gold_chunks"],
            "reference_answer": r["reference_answer"],
        }
        try:
            hits = stack_retrieve(ru, de, token)
            rec["retrieved"] = [
                {"id": h["id"], "law": h["meta"].get("law_code", ""),
                 "paragraph": h["meta"].get("paragraph", ""),
                 "doc_type": h["meta"].get("doc_type", ""),
                 "rrf_score": h.get("rrf_score")} for h in hits
            ]
            rec["distinct_parents"] = len({h["id"].split("#")[0] for h in hits})
            rec["retrieved_context"] = prompts.format_context(hits)
            rec["answer"] = generate(ru, hits, country="AT", token=token)
            rec["error"] = None
        except Exception as e:
            rec["retrieved"], rec["retrieved_context"] = rec.get("retrieved", []), ""
            rec["distinct_parents"] = 0
            rec["answer"], rec["error"] = None, f"{type(e).__name__}: {e}"
        recs.append(rec)
        print(f"  gen {rec['id']}: {'OK' if rec['answer'] else 'ERROR ' + str(rec['error'])}"
              f"  (parents={rec.get('distinct_parents')})")

    with ANSWERS_OUT.open("w", encoding="utf-8") as f:
        for rec in recs:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"wrote {ANSWERS_OUT}")

    judgeable = [r for r in recs if r.get("answer")]
    with INPUTS_OUT.open("w", encoding="utf-8") as f:
        for r in judgeable:
            f.write(json.dumps({"id": r["id"], "rubric": RUBRIC,
                                "input": build_user_block(r)}, ensure_ascii=False) + "\n")
    print(f"wrote {INPUTS_OUT}  ({len(judgeable)} judgeable)")


if __name__ == "__main__":
    main()
