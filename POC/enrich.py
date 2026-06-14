"""
Enrich each chunk with retrieval metadata (enrichment phase, step 2): a theme-tag set
(controlled vocabulary), a one-line RU summary, and 3 synthetic RU example questions
the chunk answers.

Why: the embedded text is built (embed_enriched.py) from the chunk PLUS these RU
questions, so a lay Russian question lands near a chunk that now carries lay-RU
questions in the same register — a cross-lingual bridge inside the index. Generation
still runs on the original § text, so the cited paragraph stays exact.

Model: gemini-2.5-flash (sub-task tier), strict JSON out.
Anti-leakage: questions are generated blind to the 13 eval questions; enrich_check.py
flags any synthetic question too close to a held-out test question before we trust the
numbers.

    in : data/chunks_split.jsonl
    out: data/chunks_enriched.jsonl
"""
import json
import time
from pathlib import Path

import requests

from embed_index import get_token, PROJECT, LOCATION

HERE = Path(__file__).resolve().parent
IN = HERE / "data" / "chunks_split.jsonl"
OUT = HERE / "data" / "chunks_enriched.jsonl"

MODEL = "gemini-2.5-flash"
ENDPOINT = (f"https://{LOCATION}-aiplatform.googleapis.com/v1/projects/{PROJECT}"
            f"/locations/{LOCATION}/publishers/google/models/{MODEL}:generateContent")

# Controlled vocabulary — the model must pick tags ONLY from this set (else 522 chunks
# sprout synonym tags and the facet is useless). НП can refine the wording later.
TAGS = [
    "#aufenthalt", "#daueraufenthalt", "#staatsbuergerschaft", "#asyl", "#arbeit",
    "#pass_dokumente", "#familie", "#fristen", "#gebuehren", "#verfahren",
    "#integration", "#verlust_entzug",
]

SYSTEM = """\
Ты — ассистент, который готовит МЕТАДАННЫЕ ДЛЯ ПОИСКА по корпусу австрийских законов
для беженцев и мигрантов из Беларуси. Тебе дают один фрагмент (закон на немецком или
пример консультации на русском) и его реквизиты. Сгенерируй данные, по которым живой
вопрос человека на русском найдёт именно этот фрагмент.

Верни ТОЛЬКО JSON, без пояснений:
{"keywords": ["#тег", ...], "summary_ru": "<одно предложение>", "questions_ru": ["...", "...", "..."]}

keywords: 1-3 тега СТРОГО из списка (ничего своего):
  #aufenthalt (ВНЖ, разрешения на пребывание)
  #daueraufenthalt (долгосрочное пребывание, ПМЖ)
  #staatsbuergerschaft (гражданство, натурализация)
  #asyl (убежище, статус беженца, субсидиарная защита)
  #arbeit (работа, доступ к рынку труда, RWR)
  #pass_dokumente (паспорта, проездные документы, Fremdenpass)
  #familie (воссоединение семьи)
  #fristen (сроки, действие, продление)
  #gebuehren (пошлины, сборы, стоимость)
  #verfahren (процедура, подача заявления, органы)
  #integration (язык, интеграционные требования)
  #verlust_entzug (утрата, отзыв, аннулирование статуса)

summary_ru: ОДНО предложение по-русски — что регулирует фрагмент. Без выдуманных фактов.

questions_ru — это главное. Ровно 3 вопроса (если фрагмент совсем узкий — допустимо 2),
НИКОГДА не выдумывай того, чего нет в TEXT. Правила:
  1. По-русски, как спросил бы ОБЫЧНЫЙ человек, а не юрист: житейская лексика, реальная
     ситуация («можно ли…», «что нужно, чтобы…», «у меня …, как …»). Без канцелярита.
  2. На каждый вопрос фрагмент реально даёт ответ.
  3. Три РАЗНЫХ по форме: один короткий почти ключевыми словами; один полным
     предложением; один как описание житейской ситуации.
  4. Запрещено: ссылаться на «§», «этот текст/фрагмент/закон»; упоминать имена, города,
     даты, любые персональные данные. Вопрос должен звучать самостоятельно."""


def enrich_chunk(c, token=None, retries=4, max_tokens=2048):
    token = token or get_token()
    m = c["metadata"]
    law = f"{m.get('law_code','')} {m.get('paragraph','')} — {m.get('title','')}".strip(" —")
    user = f"LAW: {law or '(пример консультации)'}\nTEXT:\n{c['text']}"
    body = {
        "systemInstruction": {"parts": [{"text": SYSTEM}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        # 2.5-flash "thinks" before emitting; too small a cap lets the thinking eat the
        # budget and truncate the JSON mid-string (same gotcha as the router). 2048 covers
        # most; a ~5% tail needs more headroom (retried at 4096).
        "generationConfig": {"temperature": 0, "maxOutputTokens": max_tokens,
                             "responseMimeType": "application/json"},
    }
    headers = {"Authorization": f"Bearer {token}", "x-goog-user-project": PROJECT,
               "Content-Type": "application/json; charset=utf-8"}
    for attempt in range(retries):
        r = requests.post(ENDPOINT, json=body, headers=headers, timeout=90)
        if r.status_code == 200:
            parts = r.json()["candidates"][0].get("content", {}).get("parts", [])
            raw = "".join(p.get("text", "") for p in parts).strip()
            d = json.loads(raw)
            kws = [k for k in d.get("keywords", []) if k in TAGS][:3]   # drop off-vocab tags
            qs = [q.strip() for q in d.get("questions_ru", []) if q.strip()][:3]
            return {"keywords": kws, "summary_ru": d.get("summary_ru", "").strip(),
                    "questions_ru": qs}
        if r.status_code in (429, 500, 503) and attempt < retries - 1:
            time.sleep(2 ** attempt)
            continue
        raise RuntimeError(f"enrich failed {r.status_code}: {r.text[:200]}")


def main():
    import concurrent.futures as cf
    rows = [json.loads(l) for l in IN.open(encoding="utf-8")]
    token = get_token()
    out = [None] * len(rows)

    def work(i):
        c = rows[i]
        try:
            c["enrich"] = enrich_chunk(c, token)
        except Exception as e:  # noqa: BLE001
            c["enrich"] = {"keywords": [], "summary_ru": "", "questions_ru": [],
                           "error": str(e)[:120]}
        return i, c

    done = 0
    with cf.ThreadPoolExecutor(max_workers=8) as ex:           # I/O-bound HTTP fan-out
        for fut in cf.as_completed([ex.submit(work, i) for i in range(len(rows))]):
            i, c = fut.result()
            out[i] = c
            done += 1
            if done % 50 == 0 or done == len(rows):
                print(f"  enriched {done}/{len(rows)}")

    with OUT.open("w", encoding="utf-8") as f:
        for c in out:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    errs = sum(1 for c in out if c["enrich"].get("error"))
    print(f"wrote {len(out)} enriched chunks -> {OUT}  (errors: {errs})")


if __name__ == "__main__":
    main()
