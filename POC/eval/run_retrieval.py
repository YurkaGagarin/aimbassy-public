"""
Retrieval evaluation harness (SICRT-style) over eval/testset.jsonl.

For every in-corpus question we embed the query, retrieve a deep ranked list, and
score the gold chunk_ids the volunteers labelled:
  - Hit Rate@k  — share of questions with >=1 primary gold chunk in the top-k.
  - MRR         — mean reciprocal rank of the first primary gold chunk.
  - Coverage@k  — SICRT recall: share of a question's primary gold chunks present
                  in the top-k (matters for multi-§ questions like q04/q13).
Metrics are stratified by difficulty (easy/difficult). Out-of-corpus questions
have no gold chunk — they are scored later by the answer judges as "correct
refusal", so they are listed here but excluded from the retrieval numbers.

q07 carries a chapter-level secondary set (8. Hauptstück FPG); we report both the
strict (primary §-anchor only) and lenient (primary+secondary) view for it.

    ~/venvs/ambassy-poc/bin/python eval/run_retrieval.py
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))   # make POC/ modules importable from eval/

from embed_index import get_token
from rag_core import retrieve

TESTSET = HERE / "testset.jsonl"
REPORT = HERE / "baseline_retrieval.md"
DEEP_K = 100          # how far down we look to find a gold (for rank/MRR)
KS = [1, 3, 5, 10]    # Hit Rate / coverage cut-offs to report
PROD_K = 5            # the retriever's production top-k (rag_core.TOP_K)


def first_rank(ranked, gold):
    """1-based rank of the first gold id in the ranked list, or None."""
    ranks = [ranked.index(g) + 1 for g in gold if g in ranked]
    return min(ranks) if ranks else None


def evaluate():
    rows = [json.loads(l) for l in TESTSET.read_text(encoding="utf-8").splitlines() if l.strip()]
    token = get_token()

    results = []
    for r in rows:
        ranked = [h["id"] for h in retrieve(r["question"], country="AT", k=DEEP_K, token=token)]
        primary = r["gold_chunks"]
        secondary = r.get("gold_chunks_secondary", [])
        rec = {
            "id": r["id"], "difficulty": r["difficulty"], "in_corpus": r["in_corpus"],
            "primary": primary, "secondary": secondary,
            "rank_primary": first_rank(ranked, primary),
            "rank_lenient": first_rank(ranked, primary + secondary),
            "top5": ranked[:PROD_K],
        }
        if primary:
            rec["hit"] = {k: any(g in ranked[:k] for g in primary) for k in KS}
            rec["coverage"] = {k: sum(g in ranked[:k] for g in primary) / len(primary) for k in KS}
            rec["rr"] = 1.0 / rec["rank_primary"] if rec["rank_primary"] else 0.0
        results.append(rec)
    return results


def summarize(results):
    incorp = [r for r in results if r["in_corpus"]]

    def agg(subset):
        if not subset:
            return None
        out = {"n": len(subset)}
        for k in KS:
            out[f"hit@{k}"] = sum(r["hit"][k] for r in subset) / len(subset)
            out[f"cov@{k}"] = sum(r["coverage"][k] for r in subset) / len(subset)
        out["mrr"] = sum(r["rr"] for r in subset) / len(subset)
        return out

    strata = {
        "ALL in-corpus": incorp,
        "easy": [r for r in incorp if r["difficulty"] == "easy"],
        "difficult": [r for r in incorp if r["difficulty"] == "difficult"],
    }
    return {name: agg(s) for name, s in strata.items()}


def fmt_report(results, summary):
    L = ["# Baseline — Retrieval (SICRT) · 2026-06-10",
         "",
         f"Corpus: 442 chunks · retriever: gemini-embedding-001 (768d, cosine) · prod top-k={PROD_K}.",
         "In-corpus questions only; out-of-corpus (refuse) judged separately.",
         "",
         "## Summary (stratified)",
         "",
         "| stratum | n | Hit@1 | Hit@3 | Hit@5 | Hit@10 | MRR | Cov@5 |",
         "|---|---|---|---|---|---|---|---|"]
    for name, s in summary.items():
        if not s:
            continue
        L.append(f"| {name} | {s['n']} | {s['hit@1']:.2f} | {s['hit@3']:.2f} | "
                 f"{s['hit@5']:.2f} | {s['hit@10']:.2f} | {s['mrr']:.2f} | {s['cov@5']:.2f} |")
    L += ["", "## Per question (in-corpus)", "",
          "| id | diff | primary gold | rank | hit@5 | note |",
          "|---|---|---|---|---|---|"]
    for r in results:
        if not r["in_corpus"]:
            continue
        rank = r["rank_primary"] if r["rank_primary"] else ">%d" % DEEP_K
        note = ""
        if r["secondary"]:
            note = f"lenient rank {r['rank_lenient']}" if r["rank_lenient"] else "secondary set"
        L.append(f"| {r['id']} | {r['difficulty']} | {','.join(r['primary'])} | "
                 f"{rank} | {'yes' if r['hit'][PROD_K] else 'NO'} | {note} |")
    L += ["", "## Out-of-corpus (expected: honest refusal — scored by judges)", ""]
    for r in results:
        if not r["in_corpus"]:
            L.append(f"- {r['id']} ({r['difficulty']}): top-1 retrieved = `{r['top5'][0]}` (no gold expected)")
    return "\n".join(L) + "\n"


def main():
    results = evaluate()
    summary = summarize(results)
    report = fmt_report(results, summary)
    REPORT.write_text(report, encoding="utf-8")

    # console view
    print(report)
    print(f"[written] {REPORT}")


if __name__ == "__main__":
    main()
