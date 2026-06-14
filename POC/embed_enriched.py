"""
Build the ENRICHED retrieval index (enrichment phase, step 3) as a SEPARATE ChromaDB
collection, so we can A/B it against the live index without touching production.

Embedded text = contextual header (law/§/title) + RU summary + theme tags + 3 synthetic
RU questions + the original chunk text. The synthetic RU questions are the cross-lingual
bridge: a lay RU query lands near the chunk. Enrichment goes FIRST so that if the
embedder truncates, it trims the original tail, not the bridge. The stored DOCUMENT
stays the ORIGINAL text, so generation and the cited § are unchanged.

    in : data/chunks_enriched.jsonl
    out: ChromaDB collection 'aimbassy_corpus_enriched' under data/chroma
"""
import concurrent.futures as cf
import json
from pathlib import Path

import chromadb
from chromadb.config import Settings

from embed_index import get_token, embed, CHROMA_PATH, clean_meta

HERE = Path(__file__).resolve().parent
IN = HERE / "data" / "chunks_enriched.jsonl"
ENRICHED_COLLECTION = "aimbassy_corpus_enriched"


def embed_text(c):
    """Text we EMBED (not what we store): enrichment first, original last."""
    m, e = c["metadata"], c.get("enrich", {})
    head = " ".join(p for p in (m.get("law_code", ""), m.get("paragraph", ""),
                                m.get("title", "")) if p).strip()
    lines = [head, e.get("summary_ru", "")]
    if e.get("keywords"):
        lines.append("Темы: " + " ".join(e["keywords"]))
    if e.get("questions_ru"):
        lines.append("Похожие вопросы: " + " / ".join(e["questions_ru"]))
    lines += ["", c["text"]]
    return "\n".join(p for p in lines if p != "" or True).strip()


def main():
    rows = [json.loads(l) for l in IN.open(encoding="utf-8")]
    token = get_token()
    embs = [None] * len(rows)

    def work(i):
        return i, embed(embed_text(rows[i]), token)

    done = 0
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        for fut in cf.as_completed([ex.submit(work, i) for i in range(len(rows))]):
            i, v = fut.result()
            embs[i] = v
            done += 1
            if done % 50 == 0 or done == len(rows):
                print(f"  embedded {done}/{len(rows)}")

    client = chromadb.PersistentClient(path=str(CHROMA_PATH),
                                       settings=Settings(anonymized_telemetry=False))
    try:
        client.delete_collection(ENRICHED_COLLECTION)   # rebuild fresh
    except Exception:
        pass
    col = client.create_collection(name=ENRICHED_COLLECTION,
                                   configuration={"hnsw": {"space": "cosine"}})

    metas = []
    for c in rows:
        m, e = dict(c["metadata"]), c.get("enrich", {})
        m["keywords"] = " ".join(e.get("keywords", []))
        m["summary"] = e.get("summary_ru", "")
        metas.append(clean_meta(m))
    col.upsert(ids=[c["id"] for c in rows], documents=[c["text"] for c in rows],
               embeddings=embs, metadatas=metas)
    print(f"indexed {col.count()} chunks into '{ENRICHED_COLLECTION}' -> {CHROMA_PATH}")


if __name__ == "__main__":
    main()
