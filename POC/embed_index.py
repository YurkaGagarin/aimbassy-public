"""
Embed the corpus (data/chunks.jsonl) with Vertex gemini-embedding-001 and store
it in a local ChromaDB collection for semantic search.

Auth (POC): gcloud user token + quota-project header — no downloaded key, no
touching the shared ADC file (CLAUDE.md). For prod the Cloud Run runtime SA is used.

Run inside the venv:
    ~/venvs/ambassy-poc/bin/python embed_index.py
"""
import json
import subprocess
import time
from pathlib import Path

import requests
import chromadb
from chromadb.config import Settings

HERE = Path(__file__).resolve().parent
CHUNKS = HERE / "data" / "chunks.jsonl"
CHROMA_PATH = HERE / "data" / "chroma"
COLLECTION = "aimbassy_corpus"

PROJECT = "aimbassy"
LOCATION = "us-central1"
MODEL = "gemini-embedding-001"
DIM = 768
ENDPOINT = (
    f"https://{LOCATION}-aiplatform.googleapis.com/v1/projects/{PROJECT}"
    f"/locations/{LOCATION}/publishers/google/models/{MODEL}:predict"
)


def get_token() -> str:
    return subprocess.check_output(
        ["gcloud", "auth", "print-access-token"], text=True
    ).strip()


def embed(text: str, token: str, task_type: str = "RETRIEVAL_DOCUMENT", retries: int = 4):
    body = {
        "instances": [{"task_type": task_type, "content": text}],
        "parameters": {"outputDimensionality": DIM, "autoTruncate": True},
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "x-goog-user-project": PROJECT,
        "Content-Type": "application/json",
    }
    for attempt in range(retries):
        r = requests.post(ENDPOINT, json=body, headers=headers, timeout=60)
        if r.status_code == 200:
            return r.json()["predictions"][0]["embeddings"]["values"]
        if r.status_code in (429, 500, 503) and attempt < retries - 1:
            time.sleep(2 ** attempt)
            continue
        raise RuntimeError(f"embed failed {r.status_code}: {r.text[:300]}")


def clean_meta(m: dict) -> dict:
    # ChromaDB rejects None values; drop them (e.g. para_sort on cases).
    return {k: v for k, v in m.items() if v is not None}


def main():
    chunks = [json.loads(l) for l in CHUNKS.open(encoding="utf-8")]
    print(f"loaded {len(chunks)} chunks")

    token = get_token()
    client = chromadb.PersistentClient(
        path=str(CHROMA_PATH), settings=Settings(anonymized_telemetry=False)
    )
    col = client.get_or_create_collection(
        name=COLLECTION, configuration={"hnsw": {"space": "cosine"}}
    )

    ids, docs, embs, metas = [], [], [], []
    for i, c in enumerate(chunks, 1):
        embs.append(embed(c["text"], token))
        ids.append(c["id"])
        docs.append(c["text"])
        metas.append(clean_meta(c["metadata"]))
        if i % 25 == 0 or i == len(chunks):
            print(f"  embedded {i}/{len(chunks)}")

    col.upsert(ids=ids, documents=docs, embeddings=embs, metadatas=metas)
    print(f"indexed {col.count()} chunks into '{COLLECTION}' -> {CHROMA_PATH}")


if __name__ == "__main__":
    main()
