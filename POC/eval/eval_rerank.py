"""
A/B retrieval eval for the Flash reranker (lever 2), stacked on RRF (lever 1).

Three conditions on the enriched (live) index, all with the SAME frozen DE rewrite:
  enr+de          frozen DE rewrite only                                  (pre-lever-1)
  enr+rrf         RRF(RU+DE) fusion                                       (lever 1)
  enr+rrf+rerank  RRF pool reranked by the Flash judge, kept top-k        (lever 2)

Reuses the PRODUCTION functions (rag_core.retrieve / retrieve_rrf, rerank.rerank), so the
eval path matches serving — the only deliberate difference is the frozen DE rewrite (the
live one is non-deterministic; freezing it isolates the lever's effect).

Question (lever 2): does reranking the deeper pool pull the buried-but-relevant statute
(q03/AuslBG-4 sat at RRF rank 6) back into the top-5 generation window, and does it lift
Hit@1, without losing the RRF case-surfacing? Gold matched by parent §.

    ~/venvs/ambassy-poc/bin/python eval/eval_rerank.py
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from embed_index import get_token
import rag_core
import rerank

TESTSET = HERE / "testset.jsonl"
REWRITES = HERE / "query_rewrites.jsonl"
REPORT = HERE / "eval_rerank.md"
DEEP_K = 60           # fused candidates pulled (rank/MRR horizon)
POOL = rerank.RERANK_POOL
KS = [1, 3, 5, 10]
PROBE_K = 5


def parent(cid):
    return cid.split("#")[0]


def parent_ranked(ids):
    seen, ranked = set(), []
    for cid in ids:
        p = parent(cid)
        if p not in seen:
            seen.add(p)
            ranked.append(p)
    return ranked


def first_rank(ranked, gold):
    rs = [ranked.index(g) + 1 for g in gold if g in ranked]
    return min(rs) if rs else None


def cases_in_top(ranked, k=PROBE_K):
    return [p for p in ranked[:k] if p.startswith("CASE")]


def main():
    token = get_token()
    rows = [json.loads(l) for l in TESTSET.read_text(encoding="utf-8").splitlines() if l.strip()]
    rw = {}
    for l in REWRITES.read_text(encoding="utf-8").splitlines():
        if l.strip():
            d = json.loads(l)
            rw[d["id"]] = d["de"]

    # Build the three parent rankings per question (production functions; frozen DE).
    rankings = {}
    for r in rows:
        ru, de = r["question"], rw[r["id"]]
        de_hits = rag_core.retrieve(de, country="AT", k=DEEP_K, token=token)
        rrf_hits = rag_core.retrieve_rrf(ru, de, country="AT", k=DEEP_K, token=token)
        # Rerank the top POOL of the fused list, keep the tail in fused order.
        reranked_pool = rerank.rerank(ru, rrf_hits[:POOL], token=token)
        rer_hits = reranked_pool + rrf_hits[POOL:]
        rankings[r["id"]] = {
            "de": parent_ranked([h["id"] for h in de_hits]),
            "rrf": parent_ranked([h["id"] for h in rrf_hits]),
            "rrf+rerank": parent_ranked([h["id"] for h in rer_hits]),
        }

    conds = ["de", "rrf", "rrf+rerank"]
    inc = [r for r in rows if r["in_corpus"]]
    summary, per_q = {}, {}
    for name in conds:
        hits = {k: 0 for k in KS}
        rr = 0.0
        for r in inc:
            ranked = rankings[r["id"]][name]
            gold = [parent(g) for g in r["gold_chunks"]]
            rank = first_rank(ranked, gold)
            per_q.setdefault(r["id"], {})[name] = rank
            for k in KS:
                hits[k] += int(any(g in ranked[:k] for g in gold))
            rr += (1.0 / rank if rank else 0.0)
        n = len(inc)
        summary[name] = {**{f"hit@{k}": hits[k] / n for k in KS}, "mrr": rr / n}

    probe = []
    for r in rows:
        probe.append({"id": r["id"], "in_corpus": r["in_corpus"],
                      **{c: cases_in_top(rankings[r["id"]][c]) for c in conds}})

    L = ["# Reranker (lever 2) — retrieval A/B on the enriched index · 2026-06-13", "",
         "Conditions (same frozen DE rewrite): `enr+de` -> `enr+rrf` (lever 1) -> "
         f"`enr+rrf+rerank` (Flash reranker over top-{POOL} pool, kept top-5). Production "
         "functions reused; gold matched by parent §.", "",
         "## 1. Statute recall (in-corpus law questions, n=%d)" % len(inc), "",
         "| condition | Hit@1 | Hit@3 | Hit@5 | Hit@10 | MRR |", "|---|---|---|---|---|---|"]
    for name in conds:
        s = summary[name]
        L.append(f"| {name} | {s['hit@1']:.2f} | {s['hit@3']:.2f} | {s['hit@5']:.2f} | "
                 f"{s['hit@10']:.2f} | {s['mrr']:.2f} |")
    L += ["", "### Per-question rank of first gold § (lower = better; '-' = not in top-%d)" % DEEP_K, "",
          "| id | de | rrf | rrf+rerank |", "|---|---|---|---|"]
    for r in inc:
        d = per_q[r["id"]]
        L.append(f"| {r['id']} | {d['de'] or '-'} | {d['rrf'] or '-'} | {d['rrf+rerank'] or '-'} |")

    L += ["", "## 2. Case surfacing (any CASE-* in top-%d)" % PROBE_K, "",
          "| id | in_corpus | de | rrf | rrf+rerank |", "|---|---|---|---|---|"]
    for p in probe:
        L.append(f"| {p['id']} | {p['in_corpus']} | {', '.join(p['de']) or '-'} | "
                 f"{', '.join(p['rrf']) or '-'} | {', '.join(p['rrf+rerank']) or '-'} |")

    report = "\n".join(L) + "\n"
    REPORT.write_text(report, encoding="utf-8")
    print(report)
    print(f"[written] {REPORT}")


if __name__ == "__main__":
    main()
