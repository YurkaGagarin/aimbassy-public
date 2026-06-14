"""
Reranker node (lever 2). Runs AFTER retrieve, BEFORE generate. A single batched
Flash call re-orders the retrieved candidate POOL by how well each chunk actually
helps answer THIS question, and we keep the top-k for generation.

Why a Flash judge-reranker and not a managed/cross-encoder reranker (measured trade-off,
2026-06-13): our core risk is cross-lingual ranking — the user's RU question against a
mix of German statutes and Russian cases. An LLM scores RU↔DE relevance natively (it
already does our rewrite and generation), needs ZERO new dependencies (no torch in the
iCloud-fragile venv, no separate Cloud Run container), and ports to prod as-is. The cost
is one extra Flash call; lever 3 (Flash-on-generate) more than offsets it. Vertex Ranking
API is the natural prod swap once its RU↔DE quality is confirmed.

What it fixes (from the RRF measurement): RRF lifted Hit@1 but diluted a statute whose
RU leg was weak (q03/AuslBG-4 drifted rank 3->6, out of the top-5 generation window). The
reranker re-scores the deeper pool by direct query-document relevance, so a buried-but-
relevant chunk can climb back, and it is robust to the non-deterministic DE rewrite jitter.

We pass the RU (scrubbed) question as the ranking query — it is the user's true intent, and
Flash handles the cross-lingual match. Candidate text is truncated for the ranking prompt
only; the FULL hit dicts (full text) are returned for generation.

Fail-safe: on any error or unusable output, return the input order unchanged (degrade to
the RRF ranking) rather than break the pipeline.

    from rerank import rerank
"""
import json
import time

import requests

from embed_index import get_token, PROJECT, LOCATION

RERANK_MODEL = "gemini-2.5-flash"
RERANK_ENDPOINT = (f"https://{LOCATION}-aiplatform.googleapis.com/v1/projects/{PROJECT}"
                   f"/locations/{LOCATION}/publishers/google/models/{RERANK_MODEL}:generateContent")

# Candidate pool the retriever hands the reranker. Deep enough to rescue a buried-but-
# relevant chunk (q03/AuslBG-4 sat at RRF rank 6, q04 at 14) without an oversized prompt;
# golds beyond this (q10 ~33) stay a residual for another lever. Reranked down to top-k.
RERANK_POOL = 20
SNIPPET_CHARS = 600     # candidate text shown to the ranker (enough to judge relevance)

RERANK_SYSTEM = """\
Du bist ein Reranker für ein juristisches Hilfe-System für Migranten in Österreich.
Gegeben sind eine NUTZERFRAGE (meist Russisch) und nummerierte KANDIDATEN-Quellen — eine
Mischung aus österreichischen Gesetzesparagraphen (Deutsch) und realen Beratungsfällen
(Russisch). Ordne die Kandidaten danach, wie gut jeder die Frage TATSÄCHLICH beantwortet.

Bewertungsregeln:
- Höchste Relevanz: der Kandidat liefert die konkrete Norm, das Verfahren, die
  Voraussetzung, die Frist oder die praktische Antwort auf GENAU diese Frage.
- Sprache ist egal: ein russischer Beratungsfall kann relevanter sein als ein deutscher
  Paragraph und umgekehrt — bewerte den INHALT, nicht die Sprache.
- Niedrige Relevanz: nur thematisch verwandt, allgemein, oder beantwortet eine andere Frage.

Gib NUR ein JSON-Objekt zurück, ohne weiteren Text:
{"ranking": [<Kandidatennummern, beste zuerst, ALLE Nummern genau einmal>]}"""


def _candidate_block(hits):
    """Number candidates 1..N with a short, language-tagged snippet for ranking."""
    lines = []
    for i, h in enumerate(hits, 1):
        m = h.get("meta", {})
        if m.get("doc_type") == "case":
            label = f"Beratungsfall (RU) — {m.get('title', '')}".strip()
        else:
            law = m.get("law_code", "")
            para = (m.get("paragraph") or "").replace("§", "").strip()
            label = f"{law} § {para} (DE) — {m.get('title', '')}".strip(" —")
        snippet = " ".join((h.get("text", "") or "").split())[:SNIPPET_CHARS]
        lines.append(f"[{i}] {label}\n{snippet}")
    return "\n\n".join(lines)


def _rank(question, hits, token, retries=4):
    user = f"NUTZERFRAGE:\n{question}\n\nKANDIDATEN:\n{_candidate_block(hits)}"
    body = {
        "systemInstruction": {"parts": [{"text": RERANK_SYSTEM}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        # 2.5-flash "thinks" before emitting; the thinking over a 20-candidate German-law
        # pool measured ~1967 tokens, which blew the old 2048 cap (finishReason MAX_TOKENS)
        # and truncated the JSON ranking -> silent fail-safe to retrieval order. The visible
        # output is tiny (a list of ints), so the cap exists almost entirely for thinking:
        # 4096 leaves headroom. Same recurring lesson as enrich/router/rag_core.
        "generationConfig": {"temperature": 0, "maxOutputTokens": 4096,
                             "responseMimeType": "application/json"},
    }
    headers = {"Authorization": f"Bearer {token}", "x-goog-user-project": PROJECT,
               "Content-Type": "application/json; charset=utf-8"}
    for attempt in range(retries):
        r = requests.post(RERANK_ENDPOINT, json=body, headers=headers, timeout=120)
        if r.status_code == 200:
            parts = r.json()["candidates"][0].get("content", {}).get("parts", [])
            raw = "".join(p.get("text", "") for p in parts).strip()
            return json.loads(raw)
        if r.status_code in (429, 500, 503) and attempt < retries - 1:
            time.sleep(2 ** attempt)
            continue
        raise RuntimeError(f"rerank {r.status_code}: {r.text[:300]}")


def _reorder(hits, ranking):
    """Apply a 1-based index ranking to hits: take valid indices in order, dedup, then
    append any candidate the judge omitted (in original order) so nothing is dropped."""
    n = len(hits)
    seen, out = set(), []
    for idx in ranking:
        if isinstance(idx, int) and 1 <= idx <= n and idx not in seen:
            seen.add(idx)
            out.append(hits[idx - 1])
    for i in range(1, n + 1):
        if i not in seen:
            out.append(hits[i - 1])
    return out


def rerank(question, hits, token=None, top_k=None):
    """Re-order `hits` by Flash-judged relevance to `question`; return the reordered list
    (sliced to top_k if given). Degrades to the input order on any failure."""
    if not hits:
        return hits
    token = token or get_token()
    try:
        v = _rank(question, hits, token)
        ranking = v.get("ranking", [])
        ordered = _reorder(hits, ranking) if ranking else list(hits)
    except (ValueError, KeyError, RuntimeError):
        ordered = list(hits)        # fail-safe: keep the retrieval order
    return ordered[:top_k] if top_k else ordered


if __name__ == "__main__":
    tok = get_token()
    demo = [
        {"meta": {"doc_type": "law", "law_code": "StbG", "paragraph": "§ 10", "title": "Verleihung"},
         "text": "Die Staatsbürgerschaft kann nach mindestens zehn Jahren rechtmäßigen Aufenthalts verliehen werden."},
        {"meta": {"doc_type": "law", "law_code": "FPG", "paragraph": "§ 88", "title": "Fremdenpass"},
         "text": "Ein Fremdenpass kann Fremden ausgestellt werden, die kein gültiges Reisedokument besitzen."},
        {"meta": {"doc_type": "case", "title": "Кейс — гражданство"},
         "text": "Клиент прожил в Австрии 12 лет, подал на гражданство, вопрос о сроке проживания."},
    ]
    q = "Сколько лет нужно прожить в Австрии для гражданства?"
    out = rerank(q, demo, tok)
    print("Q:", q)
    for i, h in enumerate(out, 1):
        m = h["meta"]
        print(f"  {i}. {m.get('law_code','')}{m.get('paragraph','')} {m.get('doc_type')} — {m.get('title','')}")
