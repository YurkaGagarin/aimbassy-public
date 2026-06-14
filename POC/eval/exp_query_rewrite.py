"""
Day-4 experiment 1: does cross-lingual query rewrite improve retrieval?

For each question we retrieve twice — with the original RU query and with the
German legal rewrite — and compare gold-chunk rank, Hit@5 and MRR (same SICRT
metric as the baseline). Out-of-corpus questions have no gold and are skipped for
metrics. Writes a before/after report and caches the rewrites for inspection.

    ~/venvs/ambassy-poc/bin/python eval/exp_query_rewrite.py
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from embed_index import get_token
from rag_core import retrieve
from query_rewrite import rewrite_query

DEEP_K = 100
PROD_K = 5


def first_rank(ranked, gold):
    ranks = [ranked.index(g) + 1 for g in gold if g in ranked]
    return min(ranks) if ranks else None


def hit(ranked, gold, k):
    return any(g in ranked[:k] for g in gold)


def rr(rank):
    return 1.0 / rank if rank else 0.0


def rrf(lists, k=60):
    """Reciprocal Rank Fusion of several ranked id-lists -> one fused id-list."""
    scores = {}
    for lst in lists:
        for i, cid in enumerate(lst):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + i + 1)
    return sorted(scores, key=lambda c: -scores[c])


def main():
    rows = [json.loads(l) for l in (HERE / "testset.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    token = get_token()

    results, rewrites = [], []
    for r in rows:
        rw = rewrite_query(r["question"], token)
        rewrites.append({"id": r["id"], "ru": r["question"], "de": rw})
        ro = [h["id"] for h in retrieve(r["question"], country="AT", k=DEEP_K, token=token)]
        rd = [h["id"] for h in retrieve(rw, country="AT", k=DEEP_K, token=token)]
        rf = rrf([ro, rd])                         # fused: original + rewrite
        gold = r["gold_chunks"]
        results.append({
            "id": r["id"], "difficulty": r["difficulty"], "in_corpus": r["in_corpus"],
            "gold": gold, "de": rw,
            "rank_o": first_rank(ro, gold), "rank_d": first_rank(rd, gold), "rank_f": first_rank(rf, gold),
            "hit_o": hit(ro, gold, PROD_K) if gold else None,
            "hit_d": hit(rd, gold, PROD_K) if gold else None,
            "hit_f": hit(rf, gold, PROD_K) if gold else None,
            "rr_o": rr(first_rank(ro, gold)) if gold else None,
            "rr_d": rr(first_rank(rd, gold)) if gold else None,
            "rr_f": rr(first_rank(rf, gold)) if gold else None,
        })

    (HERE / "query_rewrites.jsonl").write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in rewrites) + "\n", encoding="utf-8")

    inc = [r for r in results if r["in_corpus"]]
    def mean(xs):
        xs = [x for x in xs if x is not None]
        return sum(xs) / len(xs) if xs else 0.0
    agg = {
        "hit5_o": mean(r["hit_o"] for r in inc), "hit5_d": mean(r["hit_d"] for r in inc),
        "hit5_f": mean(r["hit_f"] for r in inc),
        "mrr_o": mean(r["rr_o"] for r in inc), "mrr_d": mean(r["rr_d"] for r in inc),
        "mrr_f": mean(r["rr_f"] for r in inc),
    }

    L = ["# Day-4 exp 1 — cross-lingual query rewrite (RU -> formal DE) · 2026-06-10", "",
         f"In-corpus questions: {len(inc)}. Retrieval: gemini-embedding-001, prod top-k={PROD_K}.",
         "Fused = Reciprocal Rank Fusion of the original RU and rewritten DE retrievals.", "",
         "## Before / after (in-corpus)", "",
         "| metric | original RU | rewrite DE | fused (RU+DE) |", "|---|---|---|---|",
         f"| Hit@5 | {agg['hit5_o']:.2f} | {agg['hit5_d']:.2f} | {agg['hit5_f']:.2f} |",
         f"| MRR | {agg['mrr_o']:.2f} | {agg['mrr_d']:.2f} | {agg['mrr_f']:.2f} |",
         "", "## Per question (gold rank)", "",
         "| id | diff | gold | rank RU | rank DE | rank fused | hit@5 fused |", "|---|---|---|---|---|---|---|"]
    for r in inc:
        ro = r["rank_o"] if r["rank_o"] else f">{DEEP_K}"
        rd = r["rank_d"] if r["rank_d"] else f">{DEEP_K}"
        rf = r["rank_f"] if r["rank_f"] else f">{DEEP_K}"
        L.append(f"| {r['id']} | {r['difficulty']} | {','.join(r['gold'])} | {ro} | {rd} | {rf} | "
                 f"{'yes' if r['hit_f'] else 'no'} |")
    L += ["", "## German rewrites", ""]
    for r in results:
        L.append(f"- **{r['id']}**: {r['de']}")
    report = "\n".join(L) + "\n"
    (HERE / "exp_query_rewrite.md").write_text(report, encoding="utf-8")
    print(report)
    print(f"[written] {HERE/'exp_query_rewrite.md'}")


if __name__ == "__main__":
    main()
