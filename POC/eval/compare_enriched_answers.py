"""
Enrichment phase, step 5 report: answer quality of the LIVE serving path (cur+de =
current index + German rewrite) vs the CANDIDATE (enr+de = enriched index + same
rewrite). This is the gate before pointing rag_core at the enriched index.

Reuses the Day-3/4 anchored rubric and the SAME judges. GPT was unavailable this run
(OPENAI_API_KEY not in env), so the panel is the intersection present for BOTH
conditions = {gemini, claude}. We report which judges were used so the comparison is
honest. Strata come from testset.jsonl (variant-independent).

    ~/venvs/ambassy-poc/bin/python eval/compare_enriched_answers.py
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DIMS = ["correctness", "grounding", "behavior", "overall"]
ALL_JUDGES = ["gemini", "gpt", "claude"]

LIVE = "_rewrite"     # cur+de — current live serving path
CAND = "_enriched"    # enr+de — candidate (switch the index)


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


def panels(suffix, judges):
    return {j: load(f"judge_{j}{suffix}.jsonl") for j in judges}


def per_q(suffix, judges, test):
    pan = panels(suffix, judges)
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

    # judges present in BOTH conditions (apples-to-apples). "Present" = file exists AND
    # has at least one real (non-None) score — a file of all-None (e.g. GPT when the key
    # was absent) does NOT count, else the panel would be asymmetric.
    def has_scores(suffix, j):
        d = load(f"judge_{j}{suffix}.jsonl")
        return any(r.get("overall") is not None for r in d.values())

    common = [j for j in ALL_JUDGES if has_scores(LIVE, j) and has_scores(CAND, j)]

    live_rows, live_present = per_q(LIVE, common, test)
    cand_rows, cand_present = per_q(CAND, common, test)
    live, cand = strat(live_rows), strat(cand_rows)

    def cell(b, r):
        if b is None or r is None:
            return f"{fmt(b)} → {fmt(r)}"
        d = r - b
        return f"{fmt(b)} → {fmt(r)} ({'+' if d >= 0 else ''}{d:.2f})"

    L = ["# Enrichment phase, step 5 — answer quality: cur+de (live) vs enr+de (candidate) · 2026-06-13", "",
         f"Panel = judges present for BOTH conditions: {', '.join(common)} "
         f"(GPT excluded — OPENAI_API_KEY absent this run; rewrite side has it, enriched side does not).",
         "Same anchored rubric (1-5). Only change vs live: retrieval index = enriched, query = same frozen German rewrite.",
         "Generation model + prompt + rubric identical. Gate: ship the enriched index only if quality is not worse.", "",
         "## Panel mean by stratum (cur+de → enr+de, delta)", "",
         "| stratum | correctness | grounding | behavior | overall |",
         "|---|---|---|---|---|"]
    for name in live:
        L.append(f"| {name} | " + " | ".join(cell(live[name][d], cand.get(name, {}).get(d)) for d in DIMS) + " |")

    L += ["", "## Per question (panel overall)", "",
          "| id | beh | in-corpus | cur+de | enr+de | delta |", "|---|---|---|---|---|---|"]
    cand_by = {r["id"]: r for r in cand_rows}
    for r in live_rows:
        b = r["panel_overall"]
        rv = cand_by.get(r["id"], {}).get("panel_overall")
        d = (rv - b) if (b is not None and rv is not None) else None
        L.append(f"| {r['id']} | {r['behavior']} | {'yes' if r['in_corpus'] else 'no'} | "
                 f"{fmt(b)} | {fmt(rv)} | {('+' if (d or 0) >= 0 else '') + fmt(d) if d is not None else '—'} |")

    report = "\n".join(L) + "\n"
    (HERE / "enriched_answers.md").write_text(report, encoding="utf-8")
    print(report)
    print(f"[written] {HERE / 'enriched_answers.md'}")


if __name__ == "__main__":
    main()
