"""
Day-4 exp 2 report: baseline answer quality vs rewrite-retrieval answer quality.

Reads the two judge panels (baseline judge_{j}.jsonl and rewrite judge_{j}_rewrite.jsonl,
j in gemini/gpt/claude), aggregates each to panel means per stratum with the SAME method as
score.py, and writes a before/after delta table to eval/baseline_vs_rewrite.md.

Strata come from testset.jsonl (variant-independent), so the comparison is apples-to-apples.

    ~/venvs/ambassy-poc/bin/python eval/compare_answers.py
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DIMS = ["correctness", "grounding", "behavior", "overall"]
JUDGES = ["gemini", "gpt", "claude"]


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


def panel_rows(suffix, test):
    """suffix='' for baseline, '_rewrite' for the lever. Returns list of per-question panel dicts."""
    judges = {j: load(f"judge_{j}{suffix}.jsonl") for j in JUDGES}
    present = [j for j in JUDGES if judges[j]]
    rows = []
    for qid, meta in test.items():
        rec = {"id": qid, "behavior": meta["expected_behavior"],
               "difficulty": meta["difficulty"], "in_corpus": meta["in_corpus"]}
        for d in DIMS:
            rec[f"panel_{d}"] = mean(judges[j].get(qid, {}).get(d) for j in present)
        rows.append(rec)
    return rows, present


def strat_means(rows):
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

    base_rows, base_present = panel_rows("", test)
    rw_rows, rw_present = panel_rows("_rewrite", test)
    base, rw = strat_means(base_rows), strat_means(rw_rows)

    def cell(b, r):
        if b is None or r is None:
            return f"{fmt(b)} → {fmt(r)}"
        d = r - b
        return f"{fmt(b)} → {fmt(r)} ({'+' if d >= 0 else ''}{d:.2f})"

    L = ["# Day-4 exp 2 — answer quality: baseline vs rewrite retrieval · 2026-06-10", "",
         f"Baseline judges: {', '.join(base_present)} · rewrite judges: {', '.join(rw_present)} · same anchored rubric (1-5).",
         "Only change: retrieval uses the frozen German rewrite. Generation + rubric + judges identical.", "",
         "## Panel mean by stratum (baseline → rewrite, delta)", "",
         "| stratum | correctness | grounding | behavior | overall |",
         "|---|---|---|---|---|"]
    for name in base:
        L.append(f"| {name} | " + " | ".join(cell(base[name][d], rw.get(name, {}).get(d)) for d in DIMS) + " |")

    L += ["", "## Per question (panel overall)", "",
          "| id | beh | in-corpus | base | rewrite | delta |", "|---|---|---|---|---|---|"]
    rw_by_id = {r["id"]: r for r in rw_rows}
    for r in base_rows:
        b = r["panel_overall"]
        rv = rw_by_id.get(r["id"], {}).get("panel_overall")
        d = (rv - b) if (b is not None and rv is not None) else None
        L.append(f"| {r['id']} | {r['behavior']} | {'yes' if r['in_corpus'] else 'no'} | "
                 f"{fmt(b)} | {fmt(rv)} | {('+' if (d or 0) >= 0 else '') + fmt(d) if d is not None else '—'} |")

    report = "\n".join(L) + "\n"
    (HERE / "baseline_vs_rewrite.md").write_text(report, encoding="utf-8")
    print(report)
    print(f"[written] {HERE / 'baseline_vs_rewrite.md'}")


if __name__ == "__main__":
    main()
