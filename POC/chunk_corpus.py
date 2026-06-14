"""
Chunk the Austrian law corpus into per-paragraph (§) units with metadata cards.

Rule: a new chunk starts at each bold paragraph marker `**§ N.**` (N may carry a
letter suffix, e.g. 44a; the separator after § is a non-breaking space in the
source, so we match \\s). Each chunk carries the bold title line that sits
directly above its marker and runs until the next marker. Section hierarchy
(# / ## headings) is tracked and stored. No overlap between paragraphs — each §
is a self-contained unit.

Output: POC/data/chunks.jsonl (one JSON object per line, UTF-8).
Cases are handled separately (pending PII decision) and are NOT processed here.
"""
import json
import re
import statistics
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
LAWS_DIR = DATA / "laws"
CASES_DIR = DATA / "cases"
OUT = DATA / "chunks.jsonl"

# law_code -> (filename, source_url). URLs from docs/Austria/Laws/Sources.xlsx.
# FPG switched from the §88-only JUSLINE excerpt to the full RIS FPG (FPG_88.md
# kept on disk but no longer used). AsylG 2005 added (full asylum law).
LAWS = {
    "NAG":   ("NAG.md",   "https://www.ris.bka.gv.at/GeltendeFassung.wxe?Abfrage=Bundesnormen&Gesetzesnummer=20004242"),
    "StbG":  ("StbG.md",  "https://www.ris.bka.gv.at/GeltendeFassung.wxe?Abfrage=Bundesnormen&Gesetzesnummer=10005579"),
    "FPG":   ("FPG.md",   "https://ris.bka.gv.at/GeltendeFassung.wxe?Abfrage=Bundesnormen&Gesetzesnummer=20004241&FassungVom=2026-01-22"),
    "AsylG": ("AsylG.md", "https://www.ris.bka.gv.at/geltendefassung.wxe?abfrage=bundesnormen&gesetzesnummer=20004240"),
    "AuslBG": ("AuslBG.md", "https://www.ris.bka.gv.at/GeltendeFassung.wxe?Abfrage=Bundesnormen&Gesetzesnummer=10008365"),
    # NAG-DV: implementing regulation to the NAG (Durchführungsverordnung). § 11
    # legacy conversion tables + Anlagen forms stripped at cleaning (grid noise).
    # URL reconstructed from RIS pattern (StF BGBl. II Nr. 451/2005) — verify vs Sources.xlsx.
    "NAG-DV": ("NAG-DV.md", "https://www.ris.bka.gv.at/GeltendeFassung.wxe?Abfrage=Bundesnormen&Gesetzesnummer=20004844"),
}

# Anonymized consultation cases (originals kept untouched, PII removed).
# id, anonymized filename, title
CASES = [
    ("CASE-1", "case1_anon.md", "Кейс 1 — RWR / RWRplus (вид на жительство)"),
    ("CASE-2", "case2_anon.md", "Кейс 2 — студенческий ВНЖ, продление с истёкшим паспортом"),
    ("CASE-3", "case3_anon.md", "Кейс 3 — международная защита, семья с детьми (апелляция)"),
    ("CASE-4", "case4_anon.md", "Кейс 4 — смена студенческого ВНЖ на RWR с истёкшим паспортом"),
    ("CASE-5", "case5_anon.md", "Кейс 5 — статус беженца, политическая активность (апелляция)"),
]

SECTION_RE = re.compile(r"^(#{1,3})\s+(.*\S)\s*$")            # # / ## / ### headings
PARA_RE    = re.compile(r"^\*\*§\s*(\d+[a-z]?)\.\*\*(.*)$")    # **§ 8.** ... (NBSP via \s)
BOLDLINE_RE = re.compile(r"^\*\*(.+?)\*\*\s*$")               # a whole bold line (title candidate)


def clean(text: str) -> str:
    """Drop pandoc artifacts: bold markers, backslash-escapes, non-breaking
    spaces (the char that defeated grep), and the `--` en-dash artifact."""
    text = text.replace("**", "")
    text = text.replace(" ", " ")            # non-breaking space -> normal
    text = re.sub(r"\\([.()\[\]\"'§+-])", r"\1", text)
    text = re.sub(r" -- ", " – ", text)            # pandoc en-dash -> –
    return text


def body_lines(md: str):
    """Return the law body — everything after the first '---' separator line."""
    lines = md.splitlines()
    for i, ln in enumerate(lines):
        if ln.strip() == "---":
            return lines[i + 1:]
    return lines  # no separator -> whole file


def chunk_law(law_code: str, filename: str, source_url: str):
    md = (LAWS_DIR / filename).read_text(encoding="utf-8")
    lines = body_lines(md)

    chunks = []
    h1 = h2 = ""             # nearest # and ## headings
    pending_title = ""        # bold title line seen since last marker
    cur = None                # current chunk being accumulated

    def flush():
        if cur is not None:
            cur["raw"] = "\n".join(cur["raw"]).strip()
            chunks.append(cur)

    for ln in lines:
        m_sec = SECTION_RE.match(ln)
        if m_sec:
            level, txt = len(m_sec.group(1)), m_sec.group(2).strip()
            if level == 1:
                h1 = txt
            elif level == 2:
                h2 = txt
            continue

        m_para = PARA_RE.match(ln)
        if m_para:
            flush()
            num, rest = m_para.group(1), m_para.group(2)
            section = " / ".join(p for p in (h1, h2) if p)
            cur = {
                "num": num,
                "title": pending_title,
                "section": section,
                "raw": [f"§ {num}.{rest}"],
            }
            pending_title = ""   # consumed
            continue

        m_bold = BOLDLINE_RE.match(ln)
        if m_bold and cur is None:
            # title candidate before the very first § (or between §)
            pending_title = m_bold.group(1).strip()
            continue
        if m_bold and cur is not None and not cur["raw"][-1].strip():
            # a standalone bold line inside flow -> likely next §'s title
            pending_title = m_bold.group(1).strip()
            continue

        if cur is not None:
            cur["raw"].append(ln)
        elif ln.strip():
            # non-bold text before first § (rare) -> remember as title fallback
            pending_title = pending_title or ln.strip()

    flush()

    out = []
    for c in chunks:
        title = clean(c["title"]).strip()
        text = clean(c["raw"]).strip()
        if title:
            text = f"{title}\n\n{text}"
        out.append({
            "id": f"{law_code}-{c['num']}",
            "text": text,
            "metadata": {
                "country": "AT",
                "doc_type": "law",
                "law_code": law_code,
                "paragraph": f"§ {c['num']}",
                "para_sort": int(re.match(r"\d+", c["num"]).group()),
                "section": clean(c["section"]).strip(),
                "title": title,
                "lang": "de",
                "source_url": source_url,
            },
        })
    return out


def chunk_cases():
    """Each anonymized case -> one chunk (doc_type=case, lang=ru, no §/url)."""
    out = []
    for cid, fn, title in CASES:
        text = (CASES_DIR / fn).read_text(encoding="utf-8").strip()
        out.append({
            "id": cid,
            "text": text,
            "metadata": {
                "country": "AT",
                "doc_type": "case",
                "law_code": "",
                "paragraph": "",
                "para_sort": None,
                "section": "",
                "title": title,
                "lang": "ru",
                "source_url": "",
            },
        })
    return out


def main():
    all_chunks = []
    per_law = {}
    for code, (fn, url) in LAWS.items():
        cs = chunk_law(code, fn, url)
        per_law[code] = len(cs)
        all_chunks.extend(cs)

    cases = chunk_cases()
    all_chunks.extend(cases)
    per_law["CASE"] = len(cases)

    with OUT.open("w", encoding="utf-8") as f:
        for c in all_chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    lens = [len(c["text"]) for c in all_chunks]
    print(f"wrote {len(all_chunks)} chunks -> {OUT}")
    print("per law:", per_law)
    print(f"length chars: min={min(lens)} median={int(statistics.median(lens))} "
          f"p95={int(sorted(lens)[int(len(lens)*0.95)])} max={max(lens)}")
    big = sorted(all_chunks, key=lambda c: -len(c["text"]))[:5]
    print("5 longest:", [(c["id"], len(c["text"])) for c in big])
    print(f"chunks > 3000 chars: {sum(1 for l in lens if l > 3000)}")


if __name__ == "__main__":
    main()
