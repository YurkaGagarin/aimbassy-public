"""
Cross-lingual query rewrite (Day-4 retrieval lever), promoted to a serving module
for the LangGraph graph (Day 5.5b).

A lay Russian question embeds far from the formal German statute text. This rewrites
the RU question into a short FORMAL GERMAN legal search query (translation +
lay->legalese in one step), which we then embed for retrieval. The authoritative
German corpus is never touched, so the cited § stays exact — we only change what we
search WITH. Generation and routing still run on the user's own (scrubbed) question,
so the answer stays in the user's language.

Canonical copy used in production (graph.py). The Day-4 experiment in
eval/query_rewrite.py is deliberately left untouched: its A/B is locked by frozen
rewrites (query_rewrites.jsonl) and does not depend on this module. Keep the SYSTEM
prompt here in sync if the eval one ever changes.

Gotcha (measured Day 4): gemini-2.5-flash is a "thinking" model, so the rewrite is
NON-deterministic even at temperature=0 — the wording (and thus retrieval) jitters
run-to-run. Acceptable for a live demo; a production serving path should cache the
rewrite per question or fuse N German rewrites with RRF (documented TODO).

    from rewrite import rewrite_query
"""
import time

import requests

from embed_index import get_token, PROJECT, LOCATION

REWRITE_MODEL = "gemini-2.5-flash"
ENDPOINT = (f"https://{LOCATION}-aiplatform.googleapis.com/v1/projects/{PROJECT}"
            f"/locations/{LOCATION}/publishers/google/models/{REWRITE_MODEL}:generateContent")

SYSTEM = """\
Du hilfst bei der semantischen Suche in österreichischen Gesetzen (NAG, StbG, FPG,
AsylG, AuslBG, NAG-DV), die auf Deutsch vorliegen. Formuliere die Nutzerfrage (meist
Russisch, Alltagssprache) in eine KURZE, präzise deutsche juristische Suchanfrage um.
Verwende die einschlägigen Rechtsbegriffe (z. B. Aufenthaltstitel, Niederlassungs-
bewilligung, Asylberechtigter, Fremdenpass, Verleihung der Staatsbürgerschaft).
Gib NUR die deutsche Suchanfrage aus, einen Satz, ohne Erklärung, ohne Anführungszeichen."""


def rewrite_query(question, token=None, retries=4):
    """RU (lay) question -> short formal German legal search query."""
    token = token or get_token()
    body = {
        "systemInstruction": {"parts": [{"text": SYSTEM}]},
        "contents": [{"role": "user", "parts": [{"text": question}]}],
        "generationConfig": {"temperature": 0, "maxOutputTokens": 1024},
    }
    headers = {"Authorization": f"Bearer {token}", "x-goog-user-project": PROJECT,
               "Content-Type": "application/json; charset=utf-8"}
    for attempt in range(retries):
        r = requests.post(ENDPOINT, json=body, headers=headers, timeout=60)
        if r.status_code == 200:
            parts = r.json()["candidates"][0].get("content", {}).get("parts", [])
            return "".join(p.get("text", "") for p in parts).strip()
        if r.status_code in (429, 500, 503) and attempt < retries - 1:
            time.sleep(2 ** attempt)
            continue
        raise RuntimeError(f"rewrite failed {r.status_code}: {r.text[:200]}")


if __name__ == "__main__":
    tok = get_token()
    for q in ["Можно ли получить австрийское гражданство, не выходя из белорусского?",
              "Какой тип ВНЖ выдается во время процесса?"]:
        print(f"RU: {q}\nDE: {rewrite_query(q, tok)}\n")
