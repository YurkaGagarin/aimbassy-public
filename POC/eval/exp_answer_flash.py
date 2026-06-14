"""
Lever 3 (generation): does swapping the generator gemini-2.5-pro -> gemini-2.5-flash buy
the latency we need for a responsive Telegram bot without wrecking answer quality?

Retrieval is held CONSTANT (the full RRF + rerank stack, frozen German rewrite) so the only
variable is the generator. For each question we:
  - retrieve once via the production stack,
  - generate with Pro AND Flash on the SAME hits, timing each call (latency A/B),
  - save the Flash answer for the judge panel; the Pro answer is timed only (its quality is
    already judged in answers_stack.jsonl / judge_*_stack.jsonl, so we reuse that, not re-judge).

Outputs (answers_flash.jsonl + judge_inputs_flash.jsonl carry retrieved case text -> gitignored;
flash_latency.md is latency-only, safe to commit).

    ~/venvs/ambassy-poc/bin/python eval/exp_answer_flash.py
"""
import json
import sys
import time
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
ANSWERS_OUT = HERE / "answers_flash.jsonl"
INPUTS_OUT = HERE / "judge_inputs_flash.jsonl"
LATENCY_OUT = HERE / "flash_latency.md"

# Explicit literals so the A/B keeps its meaning regardless of the rag_core default
# (the default generator flipped to Flash on 2026-06-13, lever 3).
PRO_MODEL = "gemini-2.5-pro"
FLASH_MODEL = "gemini-2.5-flash"


def stack_retrieve(ru, de, token):
    """Production retrieval stack: RRF(RU+DE) over a deep pool, then Flash rerank, top-5."""
    pool = retrieve_rrf(ru, de, country="AT", k=rerank.RERANK_POOL, token=token)
    return rerank.rerank(ru, pool, token=token, top_k=TOP_K)


def timed_generate(ru, hits, token, model):
    """Generate once; return (answer_or_None, seconds, error_or_None)."""
    t0 = time.perf_counter()
    try:
        ans = generate(ru, hits, country="AT", token=token, model=model)
        return ans, time.perf_counter() - t0, None
    except Exception as e:
        return None, time.perf_counter() - t0, f"{type(e).__name__}: {e}"


def main():
    rows = [json.loads(l) for l in TESTSET.read_text(encoding="utf-8").splitlines() if l.strip()]
    rewrites = {x["id"]: x for x in
                (json.loads(l) for l in REWRITES.read_text(encoding="utf-8").splitlines() if l.strip())}
    token = get_token()
    print(f"serving collection: {rag_core.SERVING_COLLECTION}")
    print(f"== generate Pro ({PRO_MODEL}) vs Flash ({FLASH_MODEL}) on identical RRF+rerank hits ==")

    recs, lat = [], []
    for r in rows:
        ru, de = r["question"], rewrites[r["id"]]["de"]
        hits = stack_retrieve(ru, de, token)
        pro_ans, pro_s, pro_err = timed_generate(ru, hits, token, PRO_MODEL)
        flash_ans, flash_s, flash_err = timed_generate(ru, hits, token, FLASH_MODEL)

        rec = {
            "id": r["id"], "difficulty": r["difficulty"], "in_corpus": r["in_corpus"],
            "expected_behavior": r["expected_behavior"], "question": ru, "rewrite_de": de,
            "gold_label": r["gold_label"], "gold_chunks": r["gold_chunks"],
            "reference_answer": r["reference_answer"],
            "retrieved": [
                {"id": h["id"], "law": h["meta"].get("law_code", ""),
                 "paragraph": h["meta"].get("paragraph", ""),
                 "doc_type": h["meta"].get("doc_type", ""),
                 "rrf_score": h.get("rrf_score")} for h in hits
            ],
            "distinct_parents": len({h["id"].split("#")[0] for h in hits}),
            "retrieved_context": prompts.format_context(hits),
            "answer": flash_ans, "error": flash_err,
        }
        recs.append(rec)
        lat.append({"id": r["id"], "in_corpus": r["in_corpus"], "difficulty": r["difficulty"],
                    "pro_s": pro_s, "flash_s": flash_s,
                    "pro_ok": pro_ans is not None, "flash_ok": flash_ans is not None,
                    "pro_err": pro_err, "flash_err": flash_err})
        print(f"  {r['id']}: pro {pro_s:5.1f}s {'OK' if pro_ans else 'ERR'} | "
              f"flash {flash_s:5.1f}s {'OK' if flash_ans else 'ERR'}")

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

    # latency summary (no case text -> safe to commit)
    def mean(xs):
        xs = [x for x in xs if x is not None]
        return sum(xs) / len(xs) if xs else 0.0
    pro_all = mean([x["pro_s"] for x in lat])
    flash_all = mean([x["flash_s"] for x in lat])
    L = ["# Lever 3 latency: generator Pro vs Flash on identical RRF+rerank hits", "",
         f"Retrieval held constant (RRF + Flash rerank, frozen DE rewrite). Generator only varies. "
         f"n={len(lat)}. Wall-clock of the generate() HTTP call (temperature {rag_core.TEMPERATURE}, "
         f"maxOutputTokens {rag_core.MAX_OUTPUT_TOKENS}).", "",
         f"Mean generate latency: Pro {pro_all:.1f}s -> Flash {flash_all:.1f}s "
         f"({(flash_all-pro_all):+.1f}s, {100*(flash_all-pro_all)/pro_all:+.0f}%)", "",
         "| id | in-corpus | difficulty | pro s | flash s | speedup |",
         "|---|---|---|---|---|---|"]
    for x in lat:
        sp = f"{x['pro_s']/x['flash_s']:.1f}x" if x["flash_s"] else "—"
        L.append(f"| {x['id']} | {'yes' if x['in_corpus'] else 'no'} | {x['difficulty']} | "
                 f"{x['pro_s']:.1f} | {x['flash_s']:.1f} | {sp} |")
    errs = [x for x in lat if not x["pro_ok"] or not x["flash_ok"]]
    if errs:
        L += ["", "## Errors", ""]
        for x in errs:
            L.append(f"- {x['id']}: pro={x['pro_err']} flash={x['flash_err']}")
    LATENCY_OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"wrote {LATENCY_OUT}")
    print(f"\nMEAN generate latency: Pro {pro_all:.1f}s -> Flash {flash_all:.1f}s")


if __name__ == "__main__":
    main()
