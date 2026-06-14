"""
Prompt assets for the [AI]mbassy RAG answer node.

Design decisions (see MEMORY.md, Day 2):
- MULTI-COUNTRY by design. The product will cover 10+ countries with different
  official languages and law-citation styles. So nothing here hard-codes
  "German" or Austria-only orgs. Country-specific bits (few-shots, active-country
  line) are selected by a 2-letter country code; for the POC only "AT" is filled.
- The MANDATORY legal disclaimer is appended by the application (DISCLAIMER),
  NOT produced by the model. Required text must be deterministic, not left to
  the LLM to remember. The system prompt forbids the model from writing its own.
- Few-shots are HAND-WRITTEN and must NOT overlap with the 13 eval questions in
  docs/Austria/Test Qs.xlsx (avoiding train/test leakage). Grounded examples are
  faithful to their shown mini-context (we never teach the model to fabricate);
  where we have no real law for a country yet, we fall back to a behaviour-only
  example (honest refusal) instead of inventing a citation.
"""

# Country code -> human name, for the active-country line. Extend per new country.
COUNTRY_NAMES = {
    "AT": "Австрия",
}

# Default country for the single-country POC; the UI/graph overrides per request.
DEFAULT_COUNTRY = "AT"

# --- Mandatory disclaimer, appended in code (rag_core), never by the model. ---
# Universal: no country-specific org (e.g. BBU); soft wording ("рекомендую").
DISCLAIMER = (
    "Это справочная информация для ориентира, а не юридическая консультация. "
    "По вашему конкретному случаю рекомендую обратиться к юристу или в профильную "
    "организацию помощи."
)

# --- System instruction (country-agnostic base). ----------------------------
SYSTEM_PROMPT = """\
Ты — справочный ассистент [AI]mbassy. Ты помогаешь русско- и беларускоязычным \
людям (беженцам и мигрантам) разобраться в праве страны их пребывания по темам: \
убежище, легализация, виды на жительство, гражданство, паспорт иностранца.

Тебе дают КОНТЕКСТ — фрагменты официальных правовых документов той страны, о \
которой идёт речь (законы), и обезличенные примеры консультаций. Тексты законов \
могут быть на государственном языке страны (например, немецком, польском, \
литовском). Правила ответа жёсткие:

1. Отвечай ТОЛЬКО на основе приведённого КОНТЕКСТА. Не используй свои общие знания \
   о праве. Не придумывай номера статей/параграфов, сроки, суммы и условия — если \
   чего-то нет в контексте, его для тебя не существует.
2. Подкрепляй КАЖДОЕ фактическое утверждение ссылкой на источник так, как он помечен \
   в КОНТЕКСТЕ: код закона и номер статьи/параграфа, в скобках, например «(§ 45 NAG)» \
   или «(ст. 12 [код закона])». Не смешивай источники разных стран.
3. Если в КОНТЕКСТЕ нет ответа на вопрос — честно скажи, что в доступных документах \
   этого нет, и не пытайся додумать. Предложи обратиться к координатору или юристу.
4. Фрагменты с пометкой «пример консультации» — это обезличенный опыт, а не норма \
   закона. На них можно ссылаться словами «по опыту консультаций…», но не выдавать \
   за букву закона.
5. Язык ответа — на языке вопроса пользователя (русский или беларуский), простыми \
   словами, без необъяснённого юридического жаргона. Иноязычные термины из закона \
   переводи на язык ответа, оригинал можно дать в скобках: «долгосрочное пребывание \
   (Daueraufenthalt – EU)». Сначала короткий прямой ответ, затем детали со ссылками.
6. НЕ добавляй юридическую оговорку/дисклеймер сам — её допишет приложение. Не пиши \
   фраз вроде «это не юридическая консультация».
"""


def build_system_prompt(country=None):
    """System prompt + an optional active-country line, so a multi-country corpus
    is not mixed up. Falls back to the bare base when the country is unknown."""
    name = COUNTRY_NAMES.get(country)
    if not name:
        return SYSTEM_PROMPT
    return (
        SYSTEM_PROMPT
        + f"\nСейчас вопрос касается страны: {name}. Используй только документы этой "
        + "страны; право других стран не привлекай."
    )


def format_context(hits):
    """Render retrieved chunks into a labelled CONTEXT block the model can cite.

    hits: list of {"meta": {...}, "text": str}. meta carries law_code/paragraph/
    title/doc_type/source_url produced by chunk_corpus.py.
    """
    if not hits:
        return "(контекст пуст — ничего релевантного не найдено)"
    blocks = []
    for i, h in enumerate(hits, 1):
        m = h.get("meta", {})
        if m.get("doc_type") == "case":
            head = f"[Источник {i}] пример консультации — {m.get('title', '')}".strip()
        else:
            law = m.get("law_code", "")
            para = (m.get("paragraph") or "").replace("§", "").strip()
            title = m.get("title", "")
            head = f"[Источник {i}] {law} § {para} — {title}".rstrip(" —")
        body = h.get("text", "").strip()
        url = m.get("source_url")
        tail = f"\n(ссылка: {url})" if url else ""
        blocks.append(f"{head}\n{body}{tail}")
    return "\n\n".join(blocks)


def build_user_turn(question, context_block):
    """The exact shape of a user message — identical for few-shots and real queries
    (few-shots must mirror real input, or they teach the wrong format)."""
    return f"КОНТЕКСТ:\n{context_block}\n\nВОПРОС: {question}"


# --- Few-shots, selected by country. Disjoint from the 13 eval items. --------
# AT: a faithful grounded example (real § 45 NAG text) + an honest refusal that
# names the country's actual laws.
FEWSHOTS_AT = [
    {
        "question": "Сколько лет нужно прожить в Австрии, чтобы получить статус «Daueraufenthalt – EU»?",
        "context": (
            "[Источник 1] NAG § 45 — Aufenthaltstitel „Daueraufenthalt – EU\"\n"
            "§ 45. (1) Drittstaatsangehörigen, die in den letzten fünf Jahren "
            "ununterbrochen tatsächlich niedergelassen waren, kann ein Aufenthaltstitel "
            "„Daueraufenthalt – EU\" erteilt werden, wenn sie 1. die Voraussetzungen des "
            "1. Teiles erfüllen und 2. das Modul 2 der Integrationsvereinbarung (§ 10 IntG) "
            "erfüllt haben."
        ),
        "answer": (
            "Нужно непрерывно и фактически прожить в Австрии последние 5 лет "
            "(быть «niedergelassen» — постоянно проживающим). Помимо срока, требуется "
            "выполнить условия Части 1 закона и пройти Модуль 2 интеграционного "
            "соглашения (§ 45 Abs. 1 NAG). Только при соблюдении всех трёх условий "
            "может быть выдан вид на жительство «долгосрочное пребывание – ЕС» "
            "(Daueraufenthalt – EU)."
        ),
    },
    {
        "question": "Нужна ли гражданину Беларуси виза для туристической поездки в Австрию на 10 дней?",
        "context": "(контекст пуст — ничего релевантного не найдено)",
        "answer": (
            "В доступных мне законах (NAG, StbG, FPG) этот вопрос не регулируется — "
            "они касаются видов на жительство, гражданства и паспорта иностранца, а не "
            "туристических (шенгенских) виз. Точного ответа из этих источников я дать "
            "не могу, чтобы ничего не выдумать. Рекомендую уточнить у координатора или "
            "на официальном консульском ресурсе."
        ),
    },
]

# Fallback for countries we have not curated yet: behaviour-only (honest refusal),
# which needs no real law text and stays country-agnostic.
GENERIC_FEWSHOTS = [
    {
        "question": "Нужна ли мне виза для короткой туристической поездки за границу?",
        "context": "(контекст пуст — ничего релевантного не найдено)",
        "answer": (
            "В доступных мне правовых документах по вашей стране этот вопрос не "
            "регулируется. Точного ответа из этих источников дать не могу, чтобы ничего "
            "не выдумать. Рекомендую обратиться к координатору или юристу."
        ),
    },
]

FEWSHOTS_BY_COUNTRY = {
    "AT": FEWSHOTS_AT,
}


def select_fewshots(country=None):
    """Country-specific few-shots if curated, else the generic fallback."""
    return FEWSHOTS_BY_COUNTRY.get(country, GENERIC_FEWSHOTS)
