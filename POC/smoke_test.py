"""
Smoke test for retrieval: Russian questions -> embed (RETRIEVAL_QUERY) -> search
the ChromaDB corpus -> show top-k. Checks that cross-lingual retrieval surfaces
the right German paragraphs.

    ~/venvs/ambassy-poc/bin/python smoke_test.py
"""
import chromadb
from chromadb.config import Settings

from embed_index import get_token, embed, CHROMA_PATH, COLLECTION

QUERIES = [
    "Сколько лет нужно прожить в Австрии, чтобы получить гражданство?",
    "Как получить статус долгосрочного резидента ЕС (Daueraufenthalt)?",
    "Что такое карта Rot-Weiß-Rot и кому её выдают?",
    "Можно ли продлить вид на жительство без действующего паспорта?",
    "Кому выдают паспорт иностранца (Fremdenpass)?",
    # asylum corpus (AsylG 2005 + full FPG, added 2026-06-10)
    "Как получить статус беженца (убежище) в Австрии?",
    "Что такое субсидиарная защита и кому её предоставляют?",
    "Что грозит иностранцу, если в защите отказано (депортация, высылка)?",
    # employment law (AuslBG, added 2026-06-10)
    "Можно ли иностранцу работать и нужно ли разрешение на трудоустройство?",
    # implementing regulation (NAG-DV, added 2026-06-10) — q13 gold = § 7 NAG-DV
    "Можно ли податься на ВНЖ Австрии с проездным документом другой страны?",
]


def main():
    token = get_token()
    client = chromadb.PersistentClient(
        path=str(CHROMA_PATH), settings=Settings(anonymized_telemetry=False)
    )
    col = client.get_collection(COLLECTION)

    for q in QUERIES:
        qv = embed(q, token, task_type="RETRIEVAL_QUERY")
        res = col.query(
            query_embeddings=[qv],
            n_results=5,
            include=["metadatas", "documents", "distances"],
        )
        print(f"Q: {q}")
        for rank, (cid, meta, doc, dist) in enumerate(
            zip(res["ids"][0], res["metadatas"][0], res["documents"][0], res["distances"][0]), 1
        ):
            tag = meta.get("paragraph") or meta.get("title", "")
            law = meta.get("law_code") or meta.get("doc_type", "")
            snippet = doc[:85].replace("\n", " ")
            print(f"  {rank}. [{dist:.3f}] {cid:10} {law:5} {tag:12} | {snippet}")
        print()


if __name__ == "__main__":
    main()
