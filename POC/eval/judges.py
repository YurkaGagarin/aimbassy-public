"""
Answer-quality judges (Day-3 baseline, part 2). An anchored-rubric LLM-as-judge
panel scores each cached answer (eval/answers.jsonl) on the same rubric:

  - Gemini judge  — Vertex gemini-2.5-pro (key-free, same as the generator: this
                    is what lets us measure self-preference bias).
  - GPT judge     — OpenAI gpt-5.5 (OPENAI_API_KEY, auto-loaded from .env).
  - Claude judge  — produced in-session (no Anthropic key available); this module
                    writes judge_inputs.jsonl so the same rubric is applied.

Rubric is anchored (definitions, not vibes) per the course canon (decks 3/14,
classwork 14): score 1-5 on correctness / grounding / behavior + overall.
Scoring is absolute-with-reference (we hold the expert answer); the course notes
pairwise > absolute for reliability — a documented limitation of this baseline.

    ~/venvs/ambassy-poc/bin/python eval/judges.py            # runs Gemini + GPT
"""
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import requests
from dotenv import load_dotenv
from embed_index import get_token, PROJECT, LOCATION

# Load POC/.env explicitly (HERE = eval/, so parent = POC/). Deterministic regardless
# of the cwd — find_dotenv() walked up and stopped at the first .env it met, which on
# this machine is POC/.env (without OPENAI_API_KEY), so the GPT judge silently lost its
# key. The diploma keeps its own self-contained .env; we never depend on the course one.
load_dotenv(HERE.parent / ".env")

ANSWERS = HERE / "answers.jsonl"
GEMINI_JUDGE_MODEL = "gemini-2.5-pro"
GPT_JUDGE_MODEL = os.environ.get("OPENAI_JUDGE_MODEL", "gpt-5.5")

RUBRIC = """\
You are a STRICT evaluator of an AI legal-aid assistant for Belarusian migrants in
Austria. The assistant must answer ONLY from the Austrian law excerpts it was given
("RETRIEVED CONTEXT"), cite the exact paragraph (§), and never invent paragraphs or
facts. You are given the domain expert's REFERENCE ANSWER as ground truth.

Score the ASSISTANT ANSWER on four dimensions, each an integer 1-5:

correctness — does it agree with the REFERENCE ANSWER on the substance of the law?
  5 = matches the expert's substance; 3 = partially right or misses a key point;
  1 = wrong or contradicts the expert.
grounding — are its claims and § citations supported by the RETRIEVED CONTEXT, with
  no invented paragraph numbers or facts?
  5 = every claim and citation is supported, nothing invented; 3 = mostly grounded,
  minor unsupported bits; 1 = hallucinated paragraphs or facts.
behavior — did it do the right thing for EXPECTED_BEHAVIOR?
  If "answer": 5 = a substantive grounded answer to the question.
  If "refuse": 5 = it honestly says the info is outside its sources and points the
    user to a lawyer / NGO, and does NOT fabricate a confident answer; 1 = it
    fabricated an answer as if grounded.
overall — holistic 1-5; penalise verbosity used to hide weak content; do not reward
  length.

Return ONLY a JSON object, no prose:
{"correctness":int,"grounding":int,"behavior":int,"overall":int,"rationale":"<=2 sentences"}
"""


def build_user_block(rec):
    return (
        f"EXPECTED_BEHAVIOR: {rec['expected_behavior']}\n\n"
        f"QUESTION:\n{rec['question']}\n\n"
        f"RETRIEVED CONTEXT (what the assistant was given):\n{rec['retrieved_context'] or '(nothing retrieved)'}\n\n"
        f"EXPERT REFERENCE ANSWER (ground truth):\n{rec['reference_answer']}\n\n"
        f"ASSISTANT ANSWER (under evaluation):\n{rec['answer']}"
    )


def _parse(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`").split("\n", 1)[-1]
    s, e = text.find("{"), text.rfind("}")
    return json.loads(text[s:e + 1])


def judge_gemini(rec, token, retries=4):
    endpoint = (f"https://{LOCATION}-aiplatform.googleapis.com/v1/projects/{PROJECT}"
                f"/locations/{LOCATION}/publishers/google/models/{GEMINI_JUDGE_MODEL}:generateContent")
    body = {
        "systemInstruction": {"parts": [{"text": RUBRIC}]},
        "contents": [{"role": "user", "parts": [{"text": build_user_block(rec)}]}],
        "generationConfig": {"temperature": 0, "maxOutputTokens": 4096,
                             "responseMimeType": "application/json"},
    }
    headers = {"Authorization": f"Bearer {token}", "x-goog-user-project": PROJECT,
               "Content-Type": "application/json; charset=utf-8"}
    for attempt in range(retries):
        r = requests.post(endpoint, json=body, headers=headers, timeout=120)
        if r.status_code == 200:
            parts = r.json()["candidates"][0].get("content", {}).get("parts", [])
            return _parse("".join(p.get("text", "") for p in parts))
        if r.status_code in (429, 500, 503) and attempt < retries - 1:
            time.sleep(2 ** attempt); continue
        raise RuntimeError(f"gemini judge {r.status_code}: {r.text[:200]}")


def judge_gpt(rec, retries=4):
    key = os.environ["OPENAI_API_KEY"]
    body = {"model": GPT_JUDGE_MODEL,
            "messages": [{"role": "system", "content": RUBRIC},
                         {"role": "user", "content": build_user_block(rec)}],
            "max_completion_tokens": 4000,
            "response_format": {"type": "json_object"}}
    req = urllib.request.Request("https://api.openai.com/v1/chat/completions",
                                 data=json.dumps(body).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {key}",
                                          "Content-Type": "application/json"})
    for attempt in range(retries):
        try:
            r = json.load(urllib.request.urlopen(req, timeout=120))
            return _parse(r["choices"][0]["message"]["content"])
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 503) and attempt < retries - 1:
                time.sleep(2 ** attempt); continue
            raise RuntimeError(f"gpt judge {e.code}: {e.read().decode()[:200]}")


def main():
    recs = [json.loads(l) for l in ANSWERS.read_text(encoding="utf-8").splitlines() if l.strip()]
    recs = [r for r in recs if r.get("answer")]
    token = get_token()

    # Claude judges in-session: dump the exact inputs so the same rubric is applied.
    with (HERE / "judge_inputs.jsonl").open("w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps({"id": r["id"], "rubric": RUBRIC,
                                "input": build_user_block(r)}, ensure_ascii=False) + "\n")

    for vendor, fn in [("gemini", lambda r: judge_gemini(r, token)), ("gpt", judge_gpt)]:
        out = []
        for r in recs:
            try:
                score = fn(r)
                score["error"] = None
            except Exception as e:
                score = {"correctness": None, "grounding": None, "behavior": None,
                         "overall": None, "rationale": "", "error": f"{type(e).__name__}: {e}"}
            score["id"] = r["id"]
            out.append(score)
            print(f"  [{vendor}] {r['id']}: overall={score.get('overall')} {score['error'] or ''}")
        with (HERE / f"judge_{vendor}.jsonl").open("w", encoding="utf-8") as f:
            for s in out:
                f.write(json.dumps(s, ensure_ascii=False) + "\n")
        print(f"  -> wrote judge_{vendor}.jsonl\n")


if __name__ == "__main__":
    main()
