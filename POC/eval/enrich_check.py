"""
Anti-leakage check for the synthetic enrichment questions (enrichment phase).

The synthetic RU questions get embedded into the index. If any is a near-duplicate of
a held-out eval question, the chunk carrying it would rank #1 for that test question for
the wrong reason — inflating Hit@5. The enrichment model never saw the test set; this
verifies that independence held, by lexical overlap (same language, so word-set Jaccard
on content tokens is a fair, cheap proxy).

Flags any (test question, synthetic question) pair with Jaccard >= THRESHOLD so we can
inspect / drop that synthetic question before trusting the A/B numbers.

    ~/venvs/ambassy-poc/bin/python eval/enrich_check.py
"""
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENRICHED = HERE.parent / "data" / "chunks_enriched.jsonl"
TESTSET = HERE / "testset.jsonl"
THRESHOLD = 0.6

STOP = set("и в во не на я что с со а то по как из у за от о об для это вы мы он она "
           "ли же бы мне меня мой моя если или да нет можно нужно ли есть быть".split())


def toks(s):
    return {w for w in re.findall(r"[а-яёa-z]+", s.lower()) if len(w) >= 4 and w not in STOP}


def jaccard(a, b):
    return len(a & b) / len(a | b) if (a or b) else 0.0


def main():
    tests = [json.loads(l) for l in TESTSET.read_text(encoding="utf-8").splitlines() if l.strip()]
    synth = []
    for l in ENRICHED.read_text(encoding="utf-8").splitlines():
        if not l.strip():
            continue
        c = json.loads(l)
        for q in c.get("enrich", {}).get("questions_ru", []):
            synth.append((c["id"], q, toks(q)))

    print(f"test questions: {len(tests)} · synthetic questions: {len(synth)} · threshold {THRESHOLD}")
    flagged = 0
    for t in tests:
        tt = toks(t["question"])
        best = max(synth, key=lambda s: jaccard(tt, s[2]), default=None)
        if not best:
            continue
        score = jaccard(tt, best[2])
        mark = "  <-- LEAK?" if score >= THRESHOLD else ""
        if score >= THRESHOLD:
            flagged += 1
        if score >= 0.4:   # show the close ones for eyeballing
            print(f"\n{t['id']} (gold {'in' if t['in_corpus'] else 'OUT'}): «{t['question']}»")
            print(f"   max {score:.2f} vs [{best[0]}] «{best[1]}»{mark}")
    print(f"\nflagged (>= {THRESHOLD}): {flagged}")


if __name__ == "__main__":
    main()
