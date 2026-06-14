"""
Re-judge after Настя's 2026-06-13 relabel (q02/q05/q06/q11: refuse -> answer).

The model ANSWERS did not change — only the ground-truth labels did. So only the
affected judge scores need refreshing, plus a first-time panel for the new Flash answers:

  - enriched (Pro baseline) + stack (Pro RRF+rerank): re-judge ONLY the 4 flipped ids
    (their EXPECTED_BEHAVIOR changed refuse->answer, so behavior/overall move); keep the
    other 9 scores untouched.
  - flash (RRF+rerank, gemini-2.5-flash generator): judge all 13 (never judged before).

Also patches in_corpus/expected_behavior in the answer files from testset (the single
source of truth; route_stack.py reads labels from those files) and rebuilds the
judge_inputs_*.jsonl so the Claude in-session judge sees the corrected EXPECTED_BEHAVIOR.

    ~/venvs/ambassy-poc/bin/python eval/rejudge_relabel.py
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from embed_index import get_token
from judges import judge_gemini, judge_gpt, build_user_block, RUBRIC

TESTSET = HERE / "testset.jsonl"
FLIPPED = ["q02", "q05", "q06", "q11"]
# (answers_file, suffix, ids_to_rejudge | None = all judgeable)
CONDS = [
    ("answers_enriched.jsonl", "_enriched", FLIPPED),
    ("answers_stack.jsonl",    "_stack",    FLIPPED),
    ("answers_flash.jsonl",    "_flash",    None),
]


def load(p):
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def main():
    token = get_token()
    test = {r["id"]: r for r in load(TESTSET)}

    for af, suf, ids in CONDS:
        ap = HERE / af
        if not ap.exists():
            print(f"[skip] {af} not found")
            continue
        recs = load(ap)
        # 1. patch labels from testset (answers/context unchanged)
        for r in recs:
            t = test.get(r["id"])
            if t:
                r["in_corpus"] = t["in_corpus"]
                r["expected_behavior"] = t["expected_behavior"]
        ap.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in recs) + "\n",
                      encoding="utf-8")

        judgeable = [r for r in recs if r.get("answer")]
        order = [r["id"] for r in judgeable]
        recmap = {r["id"]: r for r in judgeable}

        # 2. rebuild judge inputs with corrected EXPECTED_BEHAVIOR
        (HERE / f"judge_inputs{suf}.jsonl").write_text(
            "\n".join(json.dumps({"id": r["id"], "rubric": RUBRIC, "input": build_user_block(r)},
                                 ensure_ascii=False) for r in judgeable) + "\n", encoding="utf-8")

        targets = set(ids) if ids else set(order)
        print(f"== {suf[1:]}: re-judge {sorted(targets)} ==")

        # 3. re-judge target ids, merge into existing vendor files
        for vendor, fn in [("gemini", lambda r: judge_gemini(r, token)), ("gpt", judge_gpt)]:
            jp = HERE / f"judge_{vendor}{suf}.jsonl"
            existing = {s["id"]: s for s in load(jp)} if jp.exists() else {}
            for qid in [i for i in order if i in targets]:
                try:
                    sc = fn(recmap[qid]); sc["error"] = None
                except Exception as e:
                    sc = {"correctness": None, "grounding": None, "behavior": None,
                          "overall": None, "rationale": "", "error": f"{type(e).__name__}: {e}"}
                sc["id"] = qid
                existing[qid] = sc
                print(f"  [{vendor}{suf}] {qid}: overall={sc.get('overall')} beh={sc.get('behavior')} {sc['error'] or ''}")
            jp.write_text("\n".join(json.dumps(existing[i], ensure_ascii=False)
                                    for i in order if i in existing) + "\n", encoding="utf-8")
            print(f"  -> {jp.name} ({sum(1 for i in order if i in existing)} rows)")


if __name__ == "__main__":
    main()
