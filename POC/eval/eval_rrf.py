"""
A/B retrieval eval for the RRF(RU+DE) lever, on the enriched (live) index.

Two conditions, both on aimbassy_corpus_enriched:
  enr+de   frozen DE rewrite only (the CURRENT live serving path)         baseline
  enr+rrf  RRF fusion of the raw RU question + the frozen DE rewrite       candidate

Why two things are measured:
  1. Statute recall (the guard metric) — Hit@1/3/5/10 + MRR on the 7 in-corpus law
     questions, gold matched by PARENT § (oversized golds were sub-split, so a hit on
     any sub-chunk counts). RRF must NOT regress German-law retrieval.
  2. Case surfacing (the lever's whole point) — for every question, does any НП case
     chunk (CASE-*) appear in the top-5? The DE rewrite finds German statutes but
     embeds far from the Russian cases; RRF pulls them onto the live path. Cases are
     most relevant to the refuse questions (q02/q05/q06/q11) where the answer is
     "no statute says this — here is how it works in practice".

Uses the SAME frozen DE rewrites as the enrichment A/B (query_rewrites.jsonl), so the
DE leg is identical and the only change measured is the added RU leg + fusion.

    ~/venvs/ambassy-poc/bin/python eval/eval_rrf.py
"""
import json
import sys
from pathlib import Path

import chromadb
from chromadb.config import Settings

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from embed_index import get_token, embed, CHROMA_PATH
from embed_enriched import ENRICHED_COLLECTION
from rag_core import RRF_C

TESTSET = HERE / "testset.jsonl"
REWRITES = HERE / "query_rewrites.jsonl"
REPORT = HERE / "eval_rrf.md"
DEEP_K = 100          # candidate depth per query (also the rank/MRR horizon)
KS = [1, 3, 5, 10]
PROBE_K = 5           # top-k window for the case-surfacing probe


def parent(cid):
    return cid.split("#")[0]


def parent_ranked(ids):
    """Collapse a raw ranked id list to parents, preserving first-seen order."""
    seen, ranked = set(), []
    for cid in ids:
        p = parent(cid)
        if p not in seen:
            seen.add(p)
            ranked.append(p)
    return ranked


def query_ids(col, qv):
    res = col.query(query_embeddings=[qv], n_results=DEEP_K, where={"country": "AT"}, include=[])
    return res["ids"][0]


def rrf_fuse(list_a, list_b, c=RRF_C):
    """Reciprocal Rank Fusion of two parent-ranked lists -> one fused parent ranking.
    Mirrors rag_core.retrieve_rrf at the parent level (same Σ 1/(c+rank) formula)."""
    score = {}
    for lst in (list_a, list_b):
        for rank, p in enumerate(lst, 1):
            score[p] = score.get(p, 0.0) + 1.0 / (c + rank)
    return [p for p, _ in sorted(score.items(), key=lambda kv: kv[1], reverse=True)]


def first_rank(ranked, gold):
    rs = [ranked.index(g) + 1 for g in gold if g in ranked]
    return min(rs) if rs else None


def cases_in_top(ranked, k=PROBE_K):
    return [p for p in ranked[:k] if p.startswith("CASE")]


def main():
    token = get_token()
    client = chromadb.PersistentClient(path=str(CHROMA_PATH),
                                       settings=Settings(anonymized_telemetry=False))
    enr = client.get_collection(ENRICHED_COLLECTION)

    rows = [json.loads(l) for l in TESTSET.read_text(encoding="utf-8").splitlines() if l.strip()]
    rw = {}
    for l in REWRITES.read_text(encoding="utf-8").splitlines():
        if l.strip():
            d = json.loads(l)
            rw[d["id"]] = d["de"]

    # Per-question fused vs de-only parent rankings (compute once, reuse for both views).
    rankings = {}   # id -> {"de": [...], "rrf": [...]}
    for r in rows:
        ru_v = embed(r["question"], token, task_type="RETRIEVAL_QUERY")
        de_v = embed(rw[r["id"]], token, task_type="RETRIEVAL_QUERY")
        ru_ranked = parent_ranked(query_ids(enr, ru_v))
        de_ranked = parent_ranked(query_ids(enr, de_v))
        rankings[r["id"]] = {"de": de_ranked, "rrf": rrf_fuse(ru_ranked, de_ranked)}

    # 1) Statute recall on in-corpus law questions.
    inc = [r for r in rows if r["in_corpus"]]
    summary, per_q = {}, {}
    for name in ("de", "rrf"):
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

    # 2) Case-surfacing probe across ALL questions.
    probe = []
    for r in rows:
        de_cases = cases_in_top(rankings[r["id"]]["de"])
        rrf_cases = cases_in_top(rankings[r["id"]]["rrf"])
        probe.append({"id": r["id"], "in_corpus": r["in_corpus"],
                      "de": de_cases, "rrf": rrf_cases})
    de_q = sum(1 for p in probe if p["de"])
    rrf_q = sum(1 for p in probe if p["rrf"])

    L = ["# RRF(RU+DE) — retrieval A/B on the enriched index · 2026-06-13", "",
         "Conditions on aimbassy_corpus_enriched: `enr+de` (frozen DE rewrite only = "
         "current live path) vs `enr+rrf` (RRF fusion of raw RU question + frozen DE "
         f"rewrite, c={RRF_C}). Gold matched by parent §.", "",
         "## 1. Statute recall (in-corpus law questions, n=%d)" % len(inc), "",
         "| condition | Hit@1 | Hit@3 | Hit@5 | Hit@10 | MRR |", "|---|---|---|---|---|---|"]
    for name in ("de", "rrf"):
        s = summary[name]
        L.append(f"| {name} | {s['hit@1']:.2f} | {s['hit@3']:.2f} | {s['hit@5']:.2f} | "
                 f"{s['hit@10']:.2f} | {s['mrr']:.2f} |")
    L += ["", "### Per-question rank of first gold § (lower = better; '-' = not in top-%d)" % DEEP_K, "",
          "| id | de | rrf |", "|---|---|---|"]
    for r in inc:
        d = per_q[r["id"]]
        L.append(f"| {r['id']} | {d['de'] or '-'} | {d['rrf'] or '-'} |")

    L += ["", "## 2. Case surfacing (any CASE-* chunk in top-%d)" % PROBE_K, "",
          f"Questions with >=1 case in top-{PROBE_K}: **de={de_q}/{len(rows)} -> "
          f"rrf={rrf_q}/{len(rows)}**.", "",
          "| id | in_corpus | de | rrf |", "|---|---|---|---|"]
    for p in probe:
        L.append(f"| {p['id']} | {p['in_corpus']} | {', '.join(p['de']) or '-'} | "
                 f"{', '.join(p['rrf']) or '-'} |")

    report = "\n".join(L) + "\n"
    REPORT.write_text(report, encoding="utf-8")
    print(report)
    print(f"[written] {REPORT}")


if __name__ == "__main__":
    main()
