"""
A/B retrieval eval (enrichment phase, step 4): does the enriched index improve Hit@5?

Four conditions on the 13-question testset (only in-corpus questions are scored; the
6 out-of-corpus have no gold chunk):
  cur+ru  current index, raw RU query        (Day-3 baseline, Hit@5 ~0.14)
  cur+de  current index, frozen DE rewrite    (Day-4 lever, best so far ~0.57)
  enr+ru  enriched index, raw RU query        (does enrichment bridge WITHOUT rewrite?)
  enr+de  enriched index, frozen DE rewrite    (both levers stacked)

Gold ids are matched by PARENT (id before '#'): oversized golds (NAG-19, AuslBG-4,
StbG-10, NAG-45) were sub-split in the enriched index, so a hit on any sub-chunk counts.

    ~/venvs/ambassy-poc/bin/python eval/eval_enriched.py
"""
import json
import sys
from pathlib import Path

import chromadb
from chromadb.config import Settings

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from embed_index import get_token, embed, CHROMA_PATH, COLLECTION
from embed_enriched import ENRICHED_COLLECTION

TESTSET = HERE / "testset.jsonl"
REWRITES = HERE / "query_rewrites.jsonl"
REPORT = HERE / "eval_enriched.md"
DEEP_K = 100
KS = [1, 3, 5, 10]


def parent(cid):
    return cid.split("#")[0]


def retr(col, query, token, k=DEEP_K):
    qv = embed(query, token, task_type="RETRIEVAL_QUERY")
    res = col.query(query_embeddings=[qv], n_results=k, where={"country": "AT"}, include=[])
    # de-dup parents while preserving rank order (sub-chunks collapse to their §)
    seen, ranked = set(), []
    for cid in res["ids"][0]:
        p = parent(cid)
        if p not in seen:
            seen.add(p)
            ranked.append(p)
    return ranked


def first_rank(ranked, gold):
    rs = [ranked.index(g) + 1 for g in gold if g in ranked]
    return min(rs) if rs else None


def main():
    token = get_token()
    client = chromadb.PersistentClient(path=str(CHROMA_PATH),
                                       settings=Settings(anonymized_telemetry=False))
    cur = client.get_collection(COLLECTION)
    enr = client.get_collection(ENRICHED_COLLECTION)

    rows = [json.loads(l) for l in TESTSET.read_text(encoding="utf-8").splitlines() if l.strip()]
    rw = {}
    for l in REWRITES.read_text(encoding="utf-8").splitlines():
        if l.strip():
            d = json.loads(l)
            rw[d["id"]] = d["de"]
    inc = [r for r in rows if r["in_corpus"]]

    conds = {"cur+ru": (cur, "ru"), "cur+de": (cur, "de"),
             "enr+ru": (enr, "ru"), "enr+de": (enr, "de")}
    summary, per_q = {}, {r["id"]: {} for r in inc}
    for name, (col, src) in conds.items():
        hits = {k: 0 for k in KS}
        rr = 0.0
        for r in inc:
            q = r["question"] if src == "ru" else rw[r["id"]]
            ranked = retr(col, q, token)
            gold = [parent(g) for g in r["gold_chunks"]]
            rank = first_rank(ranked, gold)
            per_q[r["id"]][name] = rank
            for k in KS:
                hits[k] += int(any(g in ranked[:k] for g in gold))
            rr += (1.0 / rank if rank else 0.0)
        n = len(inc)
        summary[name] = {**{f"hit@{k}": hits[k] / n for k in KS}, "mrr": rr / n}

    L = ["# Enrichment A/B — retrieval (in-corpus, n=%d) · 2026-06-12" % len(inc), "",
         "Conditions: index (cur=live / enr=enriched) × query (ru=raw / de=frozen rewrite).",
         "Gold matched by parent § (sub-chunks collapse).", "",
         "| condition | Hit@1 | Hit@3 | Hit@5 | Hit@10 | MRR |", "|---|---|---|---|---|---|"]
    for name in conds:
        s = summary[name]
        L.append(f"| {name} | {s['hit@1']:.2f} | {s['hit@3']:.2f} | {s['hit@5']:.2f} | "
                 f"{s['hit@10']:.2f} | {s['mrr']:.2f} |")
    L += ["", "## Per-question rank of first gold § (lower = better; '-' = not in top-%d)" % DEEP_K, "",
          "| id | " + " | ".join(conds) + " |", "|---|" + "---|" * len(conds)]
    for r in inc:
        cells = " | ".join(str(per_q[r["id"]][n] or "-") for n in conds)
        L.append(f"| {r['id']} | {cells} |")
    report = "\n".join(L) + "\n"
    REPORT.write_text(report, encoding="utf-8")
    print(report)
    print(f"[written] {REPORT}")


if __name__ == "__main__":
    main()
