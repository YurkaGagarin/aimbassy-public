"""
Sub-split oversized law paragraphs (enrichment phase, step 1).

A handful of §§ are far larger than the embedder's ~2048-token window (gemini-
embedding-001 auto-truncates), so their tail silently never gets embedded. This
splits any law chunk over THRESHOLD chars into sub-chunks at Absatz boundaries
"(1) (2) …" (a clean legal seam, never mid-sentence), greedily packed to ~TARGET
chars, with a small Absatz-level OVERLAP so a rule that straddles a seam is not lost.

Only law chunks over THRESHOLD are touched; everything else passes through verbatim.
Sub-chunks keep the parent § in `paragraph` (so the cited § and the eval's golden
labels still resolve) and gain `parent_id` / `sub_index`. The contextual header and
the synthetic enrichment are added later (enrich.py / embed_enriched.py), not here.

    in : data/chunks.jsonl
    out: data/chunks_split.jsonl
"""
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
IN = HERE / "data" / "chunks.jsonl"
OUT = HERE / "data" / "chunks_split.jsonl"

THRESHOLD = 6000     # split law chunks longer than this many chars
TARGET = 3000        # aim for sub-chunks around this size (well under the truncation limit)
OVERLAP_CAP = 400    # carry at most this many chars of the previous Absatz as overlap

ABSATZ_RE = re.compile(r"(?m)^\(\d+[a-z]?\)\s")   # line start "(1) ", "(2a) ", …


def _hard_split(block: str, limit: int):
    """Last-resort split for a block with no usable seams (e.g. AuslBG-35 'Vollziehung'
    is one giant administrative sentence list): break on sentence boundaries, then on
    char windows, so nothing exceeds ~limit and silently truncates at embedding."""
    if len(block) <= limit:
        return [block]
    out, cur = [], ""

    def flush():
        nonlocal cur
        if cur.strip():
            out.append(cur.strip())
        cur = ""

    for part in re.split(r"(?<=[.;:])\s+", block):
        if len(part) > limit:                          # a single monster "sentence"
            flush()                                    # keep order: earlier text first
            while len(part) > limit:
                out.append(part[:limit].strip())
                part = part[limit:]
        if cur and len(cur) + len(part) > limit:
            flush()
        cur += part + " "
    flush()
    return out


def _blocks(body: str):
    """Split a § body into Absatz blocks. Falls back to blank-line paragraphs, then
    to the whole body, when there are no "(N)" markers (e.g. plain enumerations).
    Any still-oversized block is hard-split so it can never blow the embed window."""
    starts = [m.start() for m in ABSATZ_RE.finditer(body)]
    if len(starts) >= 2:
        bounds = ([0] if starts[0] > 0 else []) + starts + [len(body)]
        bounds = sorted(set(bounds))
        blocks = [body[a:b].strip() for a, b in zip(bounds, bounds[1:]) if body[a:b].strip()]
    else:
        paras = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
        blocks = paras if len(paras) >= 2 else [body.strip()]
    return [bb for b in blocks for bb in _hard_split(b, TARGET)]


def _pack(blocks):
    """Greedily pack Absatz blocks into ~TARGET-sized groups."""
    groups, cur, size = [], [], 0
    for b in blocks:
        if cur and size + len(b) > TARGET:
            groups.append(cur)
            cur, size = [], 0
        cur.append(b)
        size += len(b) + 2
    if cur:
        groups.append(cur)
    return groups


def _title_body(c):
    """Separate the leading title line(s) from the normative body so the title is not
    treated as an Absatz; it is re-attached to the first sub-chunk."""
    title = c["metadata"].get("title", "")
    text = c["text"]
    body = text[len(title):].lstrip("\n") if title and text.startswith(title) else text
    return title, body


def split_chunk(c):
    text = c["text"]
    if c["metadata"].get("doc_type") != "law" or len(text) <= THRESHOLD:
        return [c]

    title, body = _title_body(c)
    groups = _pack(_blocks(body))
    subs = []
    for i, grp in enumerate(groups):
        chunk_text = "\n\n".join(grp)
        if i > 0:
            tail = groups[i - 1][-1][-OVERLAP_CAP:]          # Absatz-level overlap
            chunk_text = f"…{tail}\n\n{chunk_text}"
        if i == 0 and title:
            chunk_text = f"{title}\n\n{chunk_text}"
        meta = dict(c["metadata"])
        meta["parent_id"] = c["id"]
        meta["sub_index"] = i
        subs.append({"id": f"{c['id']}#{i}", "text": chunk_text.strip(), "metadata": meta})
    return subs


def _norm(s):
    return re.sub(r"\s+", "", s)


def _lossless(c):
    """True iff the split blocks reconstruct the body char-for-char (ignoring
    whitespace). Packing only groups blocks and overlap/header only ADD, so a
    lossless block split guarantees a lossless final result."""
    _, body = _title_body(c)
    return _norm("".join(_blocks(body))) == _norm(body)


def main():
    rows = [json.loads(l) for l in IN.open(encoding="utf-8")]
    out, split_ids, losses = [], [], []
    for c in rows:
        subs = split_chunk(c)
        if len(subs) > 1:
            split_ids.append((c["id"], len(subs), len(c["text"])))
            if not _lossless(c):
                losses.append(c["id"])
        out.extend(subs)

    with OUT.open("w", encoding="utf-8") as f:
        for c in out:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    print(f"in={len(rows)}  out={len(out)}  split {len(split_ids)} oversized §§")
    for cid, n, ln in sorted(split_ids, key=lambda x: -x[2]):
        print(f"  {cid:12} {ln:6} chars -> {n} sub-chunks")
    newmax = max(len(c["text"]) for c in out)
    print(f"new max chunk: {newmax} chars (~{newmax//4} tok)")
    print("LINE-LOSS CHECK:", "OK (nothing lost)" if not losses else f"LOSS {losses}")


if __name__ == "__main__":
    main()
