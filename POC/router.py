"""
Router node (Day 5.3). Runs AFTER generation. A Flash judge decides whether the
generated answer is genuinely grounded in AND sufficiently answered by the retrieved
Austrian law sources for THIS question. If not (low confidence, or the sources only
tangentially relate), the answer is withheld and the user is handed off to a human
coordinator instead of receiving a confident-but-wrong answer.

Motivated by the Day-4 measurement: cross-lingual retrieval lifted in-corpus answer
quality (+0.48 correctness) but REGRESSED out-of-corpus refusals (-0.61) — the model
latched onto a plausible paragraph and answered instead of declining. The router is the
gate that turns those into honest hand-offs.

Judge: gemini-2.5-flash (stronger than -lite for the grounded/sufficient call), JSON out.
Coordinator contact is a placeholder; production reads it from env / Secret Manager.

    from router import route
"""
import json
import os
import time

import requests

from embed_index import get_token, PROJECT, LOCATION
import prompts

ROUTER_MODEL = "gemini-2.5-flash"
ROUTER_ENDPOINT = (f"https://{LOCATION}-aiplatform.googleapis.com/v1/projects/{PROJECT}"
                   f"/locations/{LOCATION}/publishers/google/models/{ROUTER_MODEL}:generateContent")

# Hand-off below this confidence, or whenever the sources don't actually answer.
CONFIDENCE_THRESHOLD = 2
COORDINATOR_CONTACT = os.environ.get("AMBASSY_COORDINATOR", "@coordinator_placeholder")

# Router rubric. v1 judged only GROUNDEDNESS. v2 (Day 5.4b) added a second test —
# grounded-but-not-actionable -> hand off (an answer that only restates a prohibition / bare
# rule when the user asked HOW to act is a dead-end). v3 (2026-06-13) adds the HONEST-REDIRECT
# exception: q11 ("permit longer than my passport") is literally impossible, but the corpus
# holds the real path (renew despite an expiring passport via Maengelheilung, Zusatzantrag
# §19/8 NAG), so Flash's "literally no, BUT here is the path" answer (3-judge panel 4.33) must
# NOT be handed off as a dead-end. Measured discipline: a first cut ALSO reworded the global
# criterion from "address THIS question" to "the underlying need" — it flipped q09 to answer
# too, but caused collateral (q01-Pro answered a genuine refuse; q02-Flash became a false
# hand-off), stable across 2 runs. So that broad rewording was REVERTED; only the SCOPED
# false-premise exception is kept. Lesson: a free-text LLM-judge rubric is not surgically
# tunable per-question — global wording drifts non-locally (we tune against 13 examples, no
# held-out). Constraint: keep in-corpus answers answered AND still hand off genuine refusals
# (q01). q09 (subjective "is it hard?", thin answer) is left to the dead-end rule on purpose.
ROUTER_SYSTEM = """\
You route a legal-aid assistant for migrants in Austria. You are given the user QUESTION,
the RETRIEVED Austrian law sources the assistant saw, and the assistant ANSWER.

Decide whether the answer is SAFE TO SEND or should be handed to a human coordinator.
A confident WRONG or DEAD-END answer is worse than an honest hand-off.

Return ONLY a JSON object, no prose:
{"answerable": <true|false>, "confidence": <1-5>, "reason": "<=1 sentence"}

Guard against TWO separate dangers:

(1) NOT GROUNDED — the assistant latched onto a plausible-looking paragraph and answered
    confidently when the retrieved sources do not actually address THIS question. If the
    real answer would require knowledge not in the retrieved sources -> answerable = false.

(2) GROUNDED BUT NOT ACTIONABLE — the question asks HOW to achieve a practical goal (get a
    permit, resolve a conflict between two rules, find a way around an obstacle), but the
    retrieved sources only state a RULE, a PROHIBITION, an eligibility bar, or a bare /
    nominal deadline — WITHOUT a concrete pathway, exception, or procedure the user could
    act on. The real answer then lives in administrative PRACTICE, not in these statutes:
    set answerable = false even though the answer is technically grounded. Do NOT reward a
    citation that only tells the user "no" or restates the obstacle when they asked "how".

EXCEPTION to (2) — HONEST REDIRECT (these are GOOD answers, do NOT hand them off). Sometimes
the QUESTION rests on a false premise or asks for something legally impossible (e.g. "how do
I get a permit valid LONGER than my passport?"). An answer that (a) corrects the premise —
"that exact thing is not possible, because ..." — AND (b) then gives a concrete, actionable
pathway to the user's REAL underlying goal (the procedure / documents / authority / exception
they can actually use) is answerable = true. Judge against the user's UNDERLYING NEED, not the
literal wording: an answer is NOT a dead-end merely because it opens by saying the literal
request is impossible. A dead-end says "no" and stops; an honest redirect says "no to X as
asked, BUT here is the real path to what you need" — that is exactly the help we want to send.

answerable = true ONLY if the sources both (a) address THIS specific question AND (b) give
  something the user can act on: a concrete procedure, a requirement / document / fee /
  authority, or a clear operative yes/no with the condition that settles it. A mere
  grounded prohibition or restatement of the obstacle is NOT actionable. (The HONEST-REDIRECT
  exception above is the one carve-out: a false-premise question answered with the real path
  to the underlying goal IS actionable.)
confidence = 1-5: how well the ANSWER is grounded in AND practically resolves THIS exact
  question (5 = fully grounded and actionable; 1 = forced, ungrounded, or a dead-end rule).
"""


def _judge(question, context, answer, token, retries=4):
    user = (f"QUESTION:\n{question}\n\nRETRIEVED SOURCES:\n{context or '(nothing retrieved)'}\n\n"
            f"ASSISTANT ANSWER:\n{answer}")
    body = {
        "systemInstruction": {"parts": [{"text": ROUTER_SYSTEM}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        # 2.5-flash "thinks" before emitting; a small cap lets the thinking eat the
        # whole budget and truncates the JSON (Unterminated string -> parse error). With 5
        # full chunks of German law in the prompt this needs headroom, like rag_core's 8192.
        # Confirmed 2026-06-13: at 2048 the judge crashed deterministically (5/5) on the
        # Flash q11 answer; route() caught it and FAIL-SAFE handed off, silently corrupting
        # the routed metric (a crash looked identical to an honest refusal). Bumped to 8192.
        "generationConfig": {"temperature": 0, "maxOutputTokens": 8192,
                             "responseMimeType": "application/json"},
    }
    headers = {"Authorization": f"Bearer {token}", "x-goog-user-project": PROJECT,
               "Content-Type": "application/json; charset=utf-8"}
    for attempt in range(retries):
        r = requests.post(ROUTER_ENDPOINT, json=body, headers=headers, timeout=120)
        if r.status_code == 200:
            parts = r.json()["candidates"][0].get("content", {}).get("parts", [])
            raw = "".join(p.get("text", "") for p in parts).strip()
            return json.loads(raw)
        if r.status_code in (429, 500, 503) and attempt < retries - 1:
            time.sleep(2 ** attempt)
            continue
        raise RuntimeError(f"router judge {r.status_code}: {r.text[:300]}")


def handoff_message(scrubbed_question):
    """The text the user gets instead of a low-confidence answer."""
    return (
        "По вашему вопросу в моих юридических источниках нет достаточной информации, "
        "чтобы дать надёжный ответ. Чтобы не ввести вас в заблуждение, передаю вопрос "
        "живому консультанту.\n\n"
        f"Контакт координатора: {COORDINATOR_CONTACT}\n"
        f"Ваш вопрос для координатора: «{scrubbed_question}»"
    )


def route(question, hits, answer, token=None):
    """Judge the answer; return a routing verdict.

    Returns:
      decision     : "answer" | "handoff"
      answerable   : bool        (sources actually contain the answer to THIS question)
      confidence   : int 1-5
      reason       : str
      final_message: what to send the user (original answer, or the hand-off text)
      error        : str | None  — exception name if the JUDGE crashed (then this hand-off is
                     a fail-safe, NOT an honest refusal); None on a real verdict. Lets logs /
                     evals tell a crash-handoff from a genuine one (a crash masquerading as a
                     refusal silently corrupted the routed eval on 2026-06-13).
    """
    token = token or get_token()
    context = prompts.format_context(hits)
    error = None
    try:
        v = _judge(question, context, answer, token)
        answerable = bool(v.get("answerable"))
        confidence = int(v.get("confidence", 0))
        reason = v.get("reason", "")
    except (ValueError, KeyError, RuntimeError) as e:
        # Fail SAFE: if the router itself fails, hand off rather than ship an unjudged answer —
        # but RECORD the crash in `error` so downstream does not count it as an honest refusal.
        answerable, confidence, reason = False, 0, f"router error: {type(e).__name__}"
        error = type(e).__name__

    handoff = (not answerable) or confidence <= CONFIDENCE_THRESHOLD
    decision = "handoff" if handoff else "answer"
    final = handoff_message(question) if handoff else answer
    return {"decision": decision, "answerable": answerable, "confidence": confidence,
            "reason": reason, "final_message": final, "error": error}


if __name__ == "__main__":
    tok = get_token()
    # ЗАВЕДОМО ВЫМЫШЛЕННЫЕ мини-кейсы.
    grounded = {
        "q": "Сколько действует паспорт иностранца (Fremdenpass)?",
        "hits": [{"meta": {"law_code": "FPG", "paragraph": "§ 90"},
                  "text": "Der Fremdenpass kann mit einer Gültigkeitsdauer von längstens fünf Jahren ausgestellt werden."}],
        "ans": "Паспорт иностранца выдаётся на срок до пяти лет (§ 90 FPG).",
    }
    forced = {
        "q": "Как получить ВНЖ на срок дольше, чем действует паспорт?",
        "hits": [{"meta": {"law_code": "NAG", "paragraph": "§ 20"},
                  "text": "Aufenthaltstitel dürfen nicht länger als das Reisedokument gültig sein."}],
        "ans": "Это невозможно: ВНЖ не может действовать дольше паспорта (§ 20 NAG).",
    }
    for case in (grounded, forced):
        v = route(case["q"], case["hits"], case["ans"], tok)
        print(f"\nQ: {case['q']}")
        print(f"  decision={v['decision']} answerable={v['answerable']} "
              f"confidence={v['confidence']} :: {v['reason']}")
