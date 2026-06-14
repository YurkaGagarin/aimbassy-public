"""
RAG core: retrieve (semantic search over ChromaDB) + generate (Vertex Gemini,
grounded answer with paragraph citations). The LangGraph graph (next step) wraps
these two functions; Streamlit calls the same functions.

Auth reuses the key-free path from embed_index (gcloud user token + quota-project
header). Generation model = gemini-2.5-pro (baseline; Flash-for-cost is a Day-4
measured lever). REST shape verified via context7 (Vertex AI generateContent).

Run inside the venv:
    ~/venvs/ambassy-poc/bin/python rag_core.py
"""
import os
import time

import requests
import chromadb
from chromadb.config import Settings

import prompts
from embed_index import get_token, embed, CHROMA_PATH, COLLECTION, PROJECT, LOCATION
from embed_enriched import ENRICHED_COLLECTION

# Serving index. Switched to the enriched collection on 2026-06-13 after the answer
# panel (eval/enriched_answers.md) showed enr+de beats cur+de on overall (3.58 -> 4.08)
# with grounding flat (4.92 -> 4.88) and no fabrication spike. Env-overridable so prod/POC
# can choose a collection without a code change, and so we can roll back to the original
# index instantly: AIMBASSY_COLLECTION=aimbassy_corpus.
SERVING_COLLECTION = os.environ.get("AIMBASSY_COLLECTION", ENRICHED_COLLECTION)

# Generator. Switched to gemini-2.5-flash on 2026-06-13 (lever 3) after the Pro-vs-Flash
# panel on the identical RRF+rerank stack (eval/flash_answers.md): generate latency
# 23.8s -> 12.5s (~2x) with in-corpus answer quality flat (overall 4.00 -> 3.97, grounding
# +0.21). Env-overridable so prod/POC can pick a generator without a code change and we can
# roll back to Pro instantly: AIMBASSY_GEN_MODEL=gemini-2.5-pro.
GEN_MODEL = os.environ.get("AIMBASSY_GEN_MODEL", "gemini-2.5-flash")


def _gen_endpoint(model):
    """Vertex generateContent endpoint for a given model. Lets generate() switch the
    generator (e.g. back to gemini-2.5-pro) without touching the default serving path
    or duplicating the URL template."""
    return (
        f"https://{LOCATION}-aiplatform.googleapis.com/v1/projects/{PROJECT}"
        f"/locations/{LOCATION}/publishers/google/models/{model}:generateContent"
    )


GEN_ENDPOINT = _gen_endpoint(GEN_MODEL)
TOP_K = 5
# RRF(RU+DE) dual-query fusion (retrieval lever). The DE rewrite finds German
# statutes well but misses the Russian НП cases (they embed near RU text); the raw
# RU question finds the cases but is weaker on statutes. We pull RRF_DEPTH candidates
# with EACH query and fuse by Reciprocal Rank Fusion. RRF_C is the standard damping
# constant from Cormack et al. 2009 (60): it flattens the contribution of deep ranks
# so a chunk ranked high by EITHER query still surfaces.
RRF_DEPTH = 30
RRF_C = 60
TEMPERATURE = 0.2
# Generous cap: 2.5-pro spends part of the budget on internal "thinking" (~1.5-2k
# tokens here). The cap must cover thinking + the visible answer, otherwise the
# reply is truncated mid-sentence (finishReason MAX_TOKENS). Measured: thinking
# ~1658 + answer ~386 hit the old 2048 cap, so we give a wide margin.
MAX_OUTPUT_TOKENS = 8192

_col = None


def get_collection():
    """Open the persistent ChromaDB serving collection once and reuse it."""
    global _col
    if _col is None:
        client = chromadb.PersistentClient(
            path=str(CHROMA_PATH), settings=Settings(anonymized_telemetry=False)
        )
        _col = client.get_collection(SERVING_COLLECTION)
    return _col


def _query(qv, country, k):
    """Run one embedded query against the serving collection; return a ranked list
    of {id, meta, text, distance}. Shared by retrieve() and retrieve_rrf()."""
    where = {"country": country} if country else None
    res = get_collection().query(
        query_embeddings=[qv],
        n_results=k,
        where=where,
        include=["metadatas", "documents", "distances"],
    )
    return [
        {"id": cid, "meta": meta, "text": doc, "distance": dist}
        for cid, meta, doc, dist in zip(
            res["ids"][0], res["metadatas"][0], res["documents"][0], res["distances"][0]
        )
    ]


def retrieve(question, country=prompts.DEFAULT_COUNTRY, k=TOP_K, token=None):
    """Embed the question (RETRIEVAL_QUERY) and return the top-k chunks for the
    given country as a list of {id, meta, text, distance}."""
    token = token or get_token()
    qv = embed(question, token, task_type="RETRIEVAL_QUERY")
    return _query(qv, country, k)


def retrieve_rrf(ru_query, de_query, country=prompts.DEFAULT_COUNTRY, k=TOP_K,
                 token=None, depth=RRF_DEPTH, c=RRF_C):
    """Dual-query Reciprocal Rank Fusion (lever 'RRF(RU+DE)').

    Retrieve `depth` candidates with the raw RU question AND the formal DE rewrite,
    then fuse: each chunk's score is Σ 1/(c + rank) over the lists it appears in, so
    a chunk ranked high by EITHER query wins. This puts the Russian НП cases (found
    by the RU query) onto the live serving path, which the DE-only rewrite misses,
    without losing the statute recall the DE query gives. Returns the top-k fused
    hits in the same shape as retrieve(), plus `rrf_score`; `distance` is the better
    (min) of the two query distances, kept only for display."""
    token = token or get_token()
    ru_v = embed(ru_query, token, task_type="RETRIEVAL_QUERY")
    de_v = embed(de_query, token, task_type="RETRIEVAL_QUERY")
    fused = {}   # id -> {"hit": dict, "score": float}
    for hits in (_query(ru_v, country, depth), _query(de_v, country, depth)):
        for rank, h in enumerate(hits, 1):
            slot = fused.setdefault(h["id"], {"hit": h, "score": 0.0})
            slot["score"] += 1.0 / (c + rank)
            if h["distance"] < slot["hit"]["distance"]:
                slot["hit"] = h
    ranked = sorted(fused.values(), key=lambda s: s["score"], reverse=True)
    out = []
    for slot in ranked[:k]:
        h = dict(slot["hit"])
        h["rrf_score"] = round(slot["score"], 5)
        out.append(h)
    return out


def _build_contents(question, hits, country):
    """Few-shot turns (country-specific) followed by the real grounded query."""
    contents = []
    for fs in prompts.select_fewshots(country):
        contents.append(
            {"role": "user", "parts": [{"text": prompts.build_user_turn(fs["question"], fs["context"])}]}
        )
        contents.append({"role": "model", "parts": [{"text": fs["answer"]}]})
    ctx = prompts.format_context(hits)
    contents.append(
        {"role": "user", "parts": [{"text": prompts.build_user_turn(question, ctx)}]}
    )
    return contents


def _call_gemini(body, token, retries=4, endpoint=None):
    endpoint = endpoint or GEN_ENDPOINT
    headers = {
        "Authorization": f"Bearer {token}",
        "x-goog-user-project": PROJECT,
        "Content-Type": "application/json; charset=utf-8",
    }
    for attempt in range(retries):
        r = requests.post(endpoint, json=body, headers=headers, timeout=120)
        if r.status_code == 200:
            return r.json()
        if r.status_code in (429, 500, 503) and attempt < retries - 1:
            time.sleep(2 ** attempt)
            continue
        raise RuntimeError(f"generate failed {r.status_code}: {r.text[:300]}")


def _extract_text(resp):
    cands = resp.get("candidates", [])
    if not cands:
        raise RuntimeError(f"no candidates; promptFeedback={resp.get('promptFeedback')}")
    cand = cands[0]
    parts = cand.get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts).strip()
    if not text:
        raise RuntimeError(f"empty answer; finishReason={cand.get('finishReason')}")
    return text


def generate(question, hits, country=prompts.DEFAULT_COUNTRY, token=None, model=GEN_MODEL):
    """Ask Gemini to answer grounded in `hits`, then append the mandatory
    disclaimer in code (never trusting the model to add it). `model` lets callers
    swap the generator (latency lever: gemini-2.5-flash) while keeping Pro the default."""
    token = token or get_token()
    body = {
        "systemInstruction": {"parts": [{"text": prompts.build_system_prompt(country)}]},
        "contents": _build_contents(question, hits, country),
        "generationConfig": {
            "temperature": TEMPERATURE,
            "maxOutputTokens": MAX_OUTPUT_TOKENS,
        },
    }
    endpoint = GEN_ENDPOINT if model == GEN_MODEL else _gen_endpoint(model)
    text = _extract_text(_call_gemini(body, token, endpoint=endpoint))
    return f"{text}\n\n{prompts.DISCLAIMER}"


def answer(question, country=prompts.DEFAULT_COUNTRY, k=TOP_K):
    """End-to-end convenience: retrieve -> generate. Shares one token."""
    token = get_token()
    hits = retrieve(question, country=country, k=k, token=token)
    text = generate(question, hits, country=country, token=token)
    return {"question": question, "country": country, "hits": hits, "answer": text}


if __name__ == "__main__":
    q = "Сколько лет нужно прожить в Австрии, чтобы получить гражданство?"
    out = answer(q)
    print("Q:", out["question"])
    print("\nНайдено (top-k):")
    for i, h in enumerate(out["hits"], 1):
        m = h["meta"]
        print(f"  {i}. [{h['distance']:.3f}] {h['id']:10} {m.get('law_code','')}/{m.get('paragraph','')} — {m.get('title','')}")
    print("\nОТВЕТ:\n")
    print(out["answer"])
