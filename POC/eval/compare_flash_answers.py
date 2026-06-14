"""
Lever 3 (generation) answer-quality A/B: same retrieval stack (RRF + rerank), generator
gemini-2.5-pro (stack) vs gemini-2.5-flash (flash). Retrieval is identical, so this isolates
the generator swap — the latency win (flash_latency.md: ~24s -> ~12s) is only worth taking
if quality holds. Same anchored rubric (1-5), same 3 judges, strata from testset (post-relabel).

    ~/venvs/ambassy-poc/bin/python eval/compare_flash_answers.py
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DIMS = ["correctness", "grounding", "behavior", "overall"]
ALL_JUDGES = ["gemini", "gpt", "claude"]

LIVE = "_stack"   # Pro generator on the RRF+rerank stack
CAND = "_flash"   # Flash generator on the SAME stack


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
    rows = []
    for qid, meta in test.items():
        rec = {"id": qid, "behavior": meta["expected_behavior"],
               "difficulty": meta["difficulty"], "in_corpus": meta["in_corpus"]}
        for d in DIMS:
            rec[f"panel_{d}"] = mean(pan[j].get(qid, {}).get(d) for j in judges)
        rows.append(rec)
    return rows


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
    live, cand = strat(per_q(LIVE, common, test)), strat(per_q(CAND, common, test))

    def cell(b, r):
        if b is None or r is None:
            return f"{fmt(b)} → {fmt(r)}"
        d = r - b
        return f"{fmt(b)} → {fmt(r)} ({'+' if d >= 0 else ''}{d:.2f})"

    L = ["# Lever 3 answer quality: Pro stack vs Flash stack (same RRF+rerank) · 2026-06-13", "",
         f"Panel = {', '.join(common)}. Same anchored rubric (1-5). Only change: generator "
         "gemini-2.5-pro → gemini-2.5-flash on identical retrieved context. Strata post-relabel "
         "(11 answer / 2 refuse). Generate latency: Pro ~23.8s → Flash ~12.5s (flash_latency.md).",
         "", "## Panel mean by stratum (Pro → Flash, delta)", "",
         "| stratum | correctness | grounding | behavior | overall |",
         "|---|---|---|---|---|"]
    for name in live:
        L.append(f"| {name} | " + " | ".join(cell(live[name][d], cand.get(name, {}).get(d)) for d in DIMS) + " |")

    L += ["", "## Per question (panel overall)", "",
          "| id | beh | in-corpus | Pro stack | Flash stack | delta |", "|---|---|---|---|---|---|"]
    live_rows = {r["id"]: r for r in per_q(LIVE, common, test)}
    cand_rows = {r["id"]: r for r in per_q(CAND, common, test)}
    for qid in test:
        b = live_rows[qid]["panel_overall"]
        rv = cand_rows[qid]["panel_overall"]
        d = (rv - b) if (b is not None and rv is not None) else None
        L.append(f"| {qid} | {test[qid]['expected_behavior']} | "
                 f"{'yes' if test[qid]['in_corpus'] else 'no'} | "
                 f"{fmt(b)} | {fmt(rv)} | {('+' if (d or 0) >= 0 else '') + fmt(d) if d is not None else '—'} |")

    report = "\n".join(L) + "\n"
    (HERE / "flash_answers.md").write_text(report, encoding="utf-8")
    print(report)
    print(f"[written] {HERE / 'flash_answers.md'}  (panel: {common})")


if __name__ == "__main__":
    main()
