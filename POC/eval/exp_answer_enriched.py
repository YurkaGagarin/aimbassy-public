"""
Enrichment phase, step 5: does switching the LIVE index to the enriched collection
lift ANSWER quality, or only the retrieval numbers (eval_enriched.md: Hit@5 0.57->0.71)?

This is the gate before we point rag_core at the enriched index. The live serving path
today is cur+de (current index + frozen German rewrite, use_rewrite default True), whose
answer panel already exists as judge_*_rewrite.jsonl. The candidate is enr+de (enriched
index + same German rewrite). Same generator, same rubric, same judges -> directly
comparable to the rewrite panel.

FAITHFUL to production: retrieval takes top-5 RAW chunks from the enriched collection
(no parent de-dup), exactly what rag_core.retrieve would return if COLLECTION were the
enriched one. Sub-chunks may collapse §-diversity in the context; we log distinct parents
per question so the report can surface any such regression. Generation still receives the
original RU question, so the user-facing answer stays Russian and the cited § stays exact.

    ~/venvs/ambassy-poc/bin/python eval/exp_answer_enriched.py
"""
import json
import sys
from pathlib import Path

import chromadb
from chromadb.config import Settings

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import prompts
from embed_index import get_token, embed, CHROMA_PATH
from embed_enriched import ENRICHED_COLLECTION
from rag_core import generate, TOP_K
from judges import judge_gemini, judge_gpt, build_user_block, RUBRIC

TESTSET = HERE / "testset.jsonl"
REWRITES = HERE / "query_rewrites.jsonl"
ANSWERS_OUT = HERE / "answers_enriched.jsonl"


def open_enriched():
    client = chromadb.PersistentClient(path=str(CHROMA_PATH),
                                       settings=Settings(anonymized_telemetry=False))
    return client.get_collection(ENRICHED_COLLECTION)


def retrieve_enriched(col, query, token, country="AT", k=TOP_K):
    """Top-k RAW chunks from the enriched index, in rag_core.retrieve's hit shape."""
    qv = embed(query, token, task_type="RETRIEVAL_QUERY")
    res = col.query(query_embeddings=[qv], n_results=k,
                    where={"country": country} if country else None,
                    include=["metadatas", "documents", "distances"])
    hits = []
    for cid, meta, doc, dist in zip(res["ids"][0], res["metadatas"][0],
                                    res["documents"][0], res["distances"][0]):
        hits.append({"id": cid, "meta": meta, "text": doc, "distance": dist})
    return hits


def generate_answers(rows, rewrites, col, token):
    out = []
    for r in rows:
        de = rewrites[r["id"]]["de"]                  # frozen German search query (enr+de)
        rec = {
            "id": r["id"], "difficulty": r["difficulty"], "in_corpus": r["in_corpus"],
            "expected_behavior": r["expected_behavior"], "question": r["question"],
            "rewrite_de": de,
            "gold_label": r["gold_label"], "gold_chunks": r["gold_chunks"],
            "reference_answer": r["reference_answer"],
        }
        try:
            hits = retrieve_enriched(col, de, token)
            rec["retrieved"] = [
                {"id": h["id"], "law": h["meta"].get("law_code", ""),
                 "paragraph": h["meta"].get("paragraph", ""), "distance": round(h["distance"], 3)}
                for h in hits
            ]
            # distinct parent § among the 5 retrieved — surfaces §-diversity loss from sub-chunks
            rec["distinct_parents"] = len({h["id"].split("#")[0] for h in hits})
            rec["retrieved_context"] = prompts.format_context(hits)
            rec["answer"] = generate(r["question"], hits, country="AT", token=token)  # answer in RU
            rec["error"] = None
        except Exception as e:
            rec["retrieved"], rec["retrieved_context"] = rec.get("retrieved", []), ""
            rec["distinct_parents"] = 0
            rec["answer"], rec["error"] = None, f"{type(e).__name__}: {e}"
        out.append(rec)
        print(f"  gen {rec['id']}: {'OK' if rec['answer'] else 'ERROR ' + rec['error']}"
              f"  (parents={rec.get('distinct_parents')})")
    return out


def main():
    rows = [json.loads(l) for l in TESTSET.read_text(encoding="utf-8").splitlines() if l.strip()]
    rewrites = {x["id"]: x for x in
                (json.loads(l) for l in REWRITES.read_text(encoding="utf-8").splitlines() if l.strip())}
    token = get_token()
    col = open_enriched()
    print(f"enriched collection: {ENRICHED_COLLECTION} ({col.count()} chunks)")

    print("== generate (enriched retrieval, enr+de) ==")
    recs = generate_answers(rows, rewrites, col, token)
    with ANSWERS_OUT.open("w", encoding="utf-8") as f:
        for rec in recs:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"wrote {ANSWERS_OUT}")

    judgeable = [r for r in recs if r.get("answer")]

    # Claude judges in-session: dump the exact inputs (same rubric as baseline/rewrite).
    with (HERE / "judge_inputs_enriched.jsonl").open("w", encoding="utf-8") as f:
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
        with (HERE / f"judge_{vendor}_enriched.jsonl").open("w", encoding="utf-8") as f:
            for s in out:
                f.write(json.dumps(s, ensure_ascii=False) + "\n")
        print(f"  -> wrote judge_{vendor}_enriched.jsonl\n")


if __name__ == "__main__":
    main()
