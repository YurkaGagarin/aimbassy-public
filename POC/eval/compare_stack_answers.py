"""
Answer-quality A/B for the retrieval stack: enr+de (current live index + frozen German
rewrite) vs enr+rrf+rerank (same index/rewrite + RRF fusion + Flash reranker).

This is the downstream gate the retrieval levers were really aiming at: do the Hit@k/MRR
gains (eval_rrf.md, eval_rerank.md) translate into better ANSWERS, or — as in Day 4 —
does better retrieval quietly hurt them? Same anchored rubric (1-5), same 3 judges. GPT
was back-filled on the enr+de side this run, so the panel is the full {gemini, gpt, claude}
present for BOTH conditions. Strata come from testset.jsonl.

    ~/venvs/ambassy-poc/bin/python eval/compare_stack_answers.py
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DIMS = ["correctness", "grounding", "behavior", "overall"]
ALL_JUDGES = ["gemini", "gpt", "claude"]

LIVE = "_enriched"   # enr+de — current live serving path (no RRF, no rerank)
CAND = "_stack"      # enr+rrf+rerank — the full retrieval stack


def load(name):
    p = HERE / name
    if not p.exists():
        return {}
    return {r["id"]: r for r in
            (json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip())}


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def fmt(x):
    return f"{x:.2f}" if isinstance(x, (int, float)) else "—"


def per_q(suffix, judges, test):
    pan = {j: load(f"judge_{j}{suffix}.jsonl") for j in judges}
    present = [j for j in judges if pan[j]]
    rows = []
    for qid, meta in test.items():
        rec = {"id": qid, "behavior": meta["expected_behavior"],
               "difficulty": meta["difficulty"], "in_corpus": meta["in_corpus"]}
        for d in DIMS:
            rec[f"panel_{d}"] = mean(pan[j].get(qid, {}).get(d) for j in present)
        rows.append(rec)
    return rows, present


def strat(rows):
    groups = {
        "ALL": rows,
        "in-corpus (answer)": [r for r in rows if r["in_corpus"]],
        "out-of-corpus (refuse)": [r for r in rows if not r["in_corpus"]],
        "easy": [r for r in rows if r["difficulty"] == "easy"],
        "difficult": [r for r in rows if r["difficulty"] == "difficult"],
    }
    return {name: {d: mean(r[f"panel_{d}"] for r in sub) for d in DIMS}
            for name, sub in groups.items() if sub}


def main():
    test = {r["id"]: r for r in
            (json.loads(l) for l in (HERE / "testset.jsonl").read_text(encoding="utf-8").splitlines() if l.strip())}

    def has_scores(suffix, j):
        d = load(f"judge_{j}{suffix}.jsonl")
        return any(r.get("overall") is not None for r in d.values())

    common = [j for j in ALL_JUDGES if has_scores(LIVE, j) and has_scores(CAND, j)]

    live_rows, _ = per_q(LIVE, common, test)
    cand_rows, _ = per_q(CAND, common, test)
    live, cand = strat(live_rows), strat(cand_rows)

    def cell(b, r):
        if b is None or r is None:
            return f"{fmt(b)} → {fmt(r)}"
        d = r - b
        return f"{fmt(b)} → {fmt(r)} ({'+' if d >= 0 else ''}{d:.2f})"

    L = ["# Retrieval-stack answer quality: enr+de (live) vs enr+rrf+rerank · 2026-06-13", "",
         f"Panel = judges present for BOTH conditions: {', '.join(common)}. Same anchored rubric "
         "(1-5). Only change vs live: retrieval = RRF(RU+DE) fusion + Flash reranker (same enriched "
         "index, same frozen German rewrite). Generator (gemini-2.5-pro) + prompt + rubric identical.",
         "", "## Panel mean by stratum (enr+de → enr+rrf+rerank, delta)", "",
         "| stratum | correctness | grounding | behavior | overall |",
         "|---|---|---|---|---|"]
    for name in live:
        L.append(f"| {name} | " + " | ".join(cell(live[name][d], cand.get(name, {}).get(d)) for d in DIMS) + " |")

    L += ["", "## Per question (panel overall)", "",
          "| id | beh | in-corpus | enr+de | stack | delta |", "|---|---|---|---|---|---|"]
    cand_by = {r["id"]: r for r in cand_rows}
    for r in live_rows:
        b = r["panel_overall"]
        rv = cand_by.get(r["id"], {}).get("panel_overall")
        d = (rv - b) if (b is not None and rv is not None) else None
        L.append(f"| {r['id']} | {r['behavior']} | {'yes' if r['in_corpus'] else 'no'} | "
                 f"{fmt(b)} | {fmt(rv)} | {('+' if (d or 0) >= 0 else '') + fmt(d) if d is not None else '—'} |")

    report = "\n".join(L) + "\n"
    (HERE / "stack_answers.md").write_text(report, encoding="utf-8")
    print(report)
    print(f"[written] {HERE / 'stack_answers.md'}  (panel: {common})")


if __name__ == "__main__":
    main()
