"""
Telegram front-end (Day 6.1) over the LangGraph graph. Polling — the simplest path to
a working bot for the demo/video; a Cloud Run webhook is an optional stretch (6.4).

Each text message runs the full pipeline (guardrail -> rewrite -> retrieve -> generate
-> router) via graph.ask(). The user gets `final`: the grounded answer, a human
hand-off, or a polite refusal. The raw message is never stored — only the DLP-scrubbed
text and metrics go to BigQuery (privacy rule), with a hashed user id.

graph.ask() is synchronous and network-heavy, so it runs in a worker thread
(asyncio.to_thread) to keep the bot responsive. Token + coordinator contact come from
POC/.env (gitignored). API verified via context7 (python-telegram-bot 22.x).

Run inside the venv:
    ~/venvs/ambassy-poc/bin/python telegram_bot.py
"""
import asyncio
import logging
import os
import time
from collections import defaultdict, deque
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (ApplicationBuilder, CommandHandler, ContextTypes,
                          MessageHandler, filters)

import graph as g
import bq_log

load_dotenv(Path(__file__).resolve().parent / ".env")

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s %(message)s", level=logging.INFO)
# httpx logs every request URL at INFO — and the Telegram URL embeds the bot token.
# Silence it so the secret never lands in a log file. (Same reason: telegram.request.)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("ambassy.bot")

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TG_LIMIT = 4000   # Telegram hard limit is 4096; leave headroom.

WELCOME = (
    "Здравствуйте! Я помогаю разобраться с легализацией, убежищем, ВНЖ, гражданством "
    "и работой в Австрии — со ссылками на конкретные параграфы законов.\n\n"
    "Задайте вопрос обычными словами (по-русски или по-беларусски). Это справочная "
    "информация, а не юридическая консультация.\n\n"
    "Пожалуйста, не присылайте лишние личные данные. Если они попадут в сообщение, "
    "я удаляю их автоматически перед обработкой."
)

# Friendly RU names for the DLP / backstop info-types, for the PII notice to the user.
PII_LABELS = {
    "PERSON_NAME": "имя", "PHONE_NUMBER": "телефон", "EMAIL_ADDRESS": "email",
    "STREET_ADDRESS": "адрес", "PASSPORT": "номер паспорта", "IBAN_CODE": "номер счёта (IBAN)",
    "DATE_OF_BIRTH": "дату рождения", "CREDIT_CARD_NUMBER": "номер карты",
    "SVNR": "страховой номер", "FILE_NO": "номер дела",
}


def _pii_notice(pii_types):
    labels = [PII_LABELS.get(t, t.lower()) for t in (pii_types or [])]
    human = ", ".join(labels) if labels else "личные данные"
    return (
        f"Заметил в вашем сообщении личные данные ({human}). Я автоматически удалил их "
        "перед обработкой — не использую и не сохраняю. Отвечаю только на суть вопроса."
    )

# --- simple in-memory rate limit (6.3). Prod -> Firestore counter (CLAUDE.md). ---
RATE_MAX = 8           # messages ...
RATE_WINDOW = 60.0     # ... per this many seconds, per user
_hits = defaultdict(deque)


def _rate_ok(user_id):
    now = time.monotonic()
    dq = _hits[user_id]
    while dq and now - dq[0] > RATE_WINDOW:
        dq.popleft()
    if len(dq) >= RATE_MAX:
        return False
    dq.append(now)
    return True


def _chunks(text):
    """Split a long answer into Telegram-sized pieces, preferring newline breaks."""
    text = text.replace("**", "")           # plain text: drop markdown bold markers
    while text:
        if len(text) <= TG_LIMIT:
            yield text
            return
        cut = text.rfind("\n", 0, TG_LIMIT)
        if cut <= 0:
            cut = TG_LIMIT
        yield text[:cut]
        text = text[cut:].lstrip("\n")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(WELCOME)


async def non_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Пожалуйста, опишите вопрос текстом.")


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id
    text = (update.message.text or "").strip()
    if not text:
        return
    if not _rate_ok(user.id):
        await update.message.reply_text(
            "Слишком много запросов подряд. Подождите минуту, пожалуйста.")
        return

    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    t0 = time.perf_counter()
    try:
        out = await asyncio.to_thread(g.ask, text)      # blocking pipeline off the event loop
    except Exception:                                    # noqa: BLE001
        log.exception("pipeline error")
        await update.message.reply_text(
            "Извините, произошла техническая ошибка. Попробуйте, пожалуйста, ещё раз позже.")
        return
    dt = time.perf_counter() - t0

    # If the message carried PII, tell the user FIRST that it was scrubbed and not stored,
    # then send the actual answer (separate message, as requested).
    gv = out.get("guard", {})
    if gv.get("pii_found"):
        await update.message.reply_text(_pii_notice(gv.get("pii_types", [])))

    final = out.get("final") or out.get("answer") or \
        "Извините, не удалось сформировать ответ."
    for piece in _chunks(final):
        await update.message.reply_text(piece, disable_web_page_preview=True)

    bq_log.log_interaction(user_id=user.id, out=out, latency_s=dt)   # privacy-safe, self-disabling


def main():
    if not TOKEN or TOKEN.startswith("PASTE_"):
        raise SystemExit("TELEGRAM_BOT_TOKEN is not set in POC/.env")
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), on_message))
    app.add_handler(MessageHandler(~filters.TEXT, non_text))
    log.info("bot starting (polling)…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
