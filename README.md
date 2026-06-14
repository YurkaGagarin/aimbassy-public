# [AI]mbassy

**Foreign law, in the language of the people who need it.**

An agentic RAG assistant that answers Austrian immigration / asylum / legalization
questions in Russian and Belarusian, grounding every answer in the exact paragraph
(§) of Austrian law — even though those laws exist only in German.

Built as a course final project together with the **Народныя Пасольствы**
(People's Embassies) network. Proof-of-concept; demo bot: **@AImbassy_bot**.

---

## The problem

- Since 2020, around **1 million** of Belarus's **8 million** people have been forced
  to leave; many settled across the EU, including Austria.
- The answers they need are buried in Austrian laws (NAG, AsylG, FPG, StbG, AuslBG,
  NAG-DV) — **German only**.
- Their questions arrive in **Russian / Belarusian**. That language gap, plus
  overloaded volunteer coordinators answering the same questions repeatedly, is the
  gap this project closes.

## How it works

A LangGraph pipeline; each node runs the cheapest Gemini model that holds quality:

```
Telegram → Guardrail → Rewrite → Retrieve → Rerank → Generate → Router → reply
```

| Node      | What it does                              | Model                       |
|-----------|-------------------------------------------|-----------------------------|
| Guardrail | DLP PII scrub + topic / injection gate    | gemini-2.5-flash-lite       |
| Rewrite   | RU/BY question → formal German query       | gemini-2.5-flash            |
| Retrieve  | Chroma, dual-query RRF fusion (RU + DE)    | gemini-embedding-001 (768d) |
| Rerank    | reorder candidates, keep the best          | gemini-2.5-flash            |
| Generate  | grounded answer citing the exact §         | gemini-2.5-flash            |
| Router    | answer vs. honest human hand-off           | gemini-2.5-flash            |

Every node emits a **privacy-safe trace** (no original message, no PII) to BigQuery.

### The RAG, briefly

- **Corpus:** 557 chunks — 552 law paragraphs across 6 Austrian laws + 5 anonymized
  consultation cases (Russian).
- **Chunking:** 1 § = 1 chunk; oversized paragraphs are split along *Absatz* seams
  with overlap.
- **Cross-lingual bridge:** each chunk is enriched with **3 synthetic Russian
  questions** embedded alongside the German §, so a live Russian question lands next
  to Russian text in the index — the key trick that makes RU→DE retrieval work.

## Results

13-question control set from the domain expert; answer quality scored by an
independent 3-judge panel (Gemini + GPT + Claude — no model grades itself).

| Metric                          | Baseline | Final  |
|---------------------------------|---------:|-------:|
| Retrieval Hit@5                 |     0.14 |   0.57 |
| Retrieval MRR                   |     0.21 |   0.56 |
| In-corpus answer quality (1–5)  |      2.9 |    4.4 |
| Generation latency              |   23.8 s | 12.5 s |

The honest story — including regressions (better retrieval briefly *hurt* refusals)
and where we stopped because n=13 hits the noise floor — is in the presentation.

## Repository layout

```
POC/
  graph.py          LangGraph pipeline (guardrail→rewrite→retrieve→rerank→generate→router)
  guardrail.py      DLP scrub + Flash-Lite topic/injection
  rewrite.py        cross-lingual query rewrite
  rag_core.py       retrieval + RRF fusion
  rerank.py         Flash judge-reranker
  router.py         answer vs. human hand-off
  enrich.py         synthetic-question chunk enrichment
  chunk_corpus.py   per-§ chunker with metadata cards
  embed_index.py    Chroma index build (Vertex embeddings)
  telegram_bot.py   Telegram interface (polling)
  app.py            Streamlit debug / demo panel
  bq_log.py         privacy-safe BigQuery tracing
  eval/             evaluation harness + judge scores + reports
  presentation/     pitch deck (index.html) + speech (RU / Hebrew)
00–06 *.md          design docs (Russian);  en/  English mirror
```

## Running locally

**Prerequisites**

- Python 3.13
- Google Cloud SDK (`gcloud`), authenticated, with a GCP project that has Vertex AI
  and DLP enabled. With user credentials, Vertex requires the quota-project header
  (`X-Goog-User-Project`); set your project id accordingly.
- A Telegram bot token from [@BotFather](https://t.me/BotFather).

**Setup**

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp POC/.env.example POC/.env     # fill TELEGRAM_BOT_TOKEN and AMBASSY_COORDINATOR
```

**Corpus** — the legal corpus and the Chroma index are **not** shipped (size +
case privacy). Provide your own source texts, then build the index:

```bash
cd POC
python chunk_corpus.py    # per-§ chunks with metadata
python enrich.py          # 3 synthetic Russian questions per chunk
python embed_index.py     # build the Chroma index (Vertex embeddings)
```

**Run**

```bash
cd POC
python telegram_bot.py    # Telegram bot (polling)
# or
streamlit run app.py      # local debug / demo panel
```

## Privacy & safety

- The user's **original message is never stored** — only DLP-scrubbed text flows
  downstream and into logs.
- **No real consultation data** is in this repo; the shipped cases are anonymized /
  synthetic.
- Secrets live only in `.env` / Secret Manager — never in code or git history.

## Presentation

Open `POC/presentation/index.html` in a browser (self-contained; `→` / `space` to
advance, `P` to print to PDF). Speech scripts: `SPEECH.ru.md` (Russian) and
`SPEECH.he.md` (Hebrew, RTL).

## Credits

Built by Alexander Fruman with the Народныя Пасольствы (People's Embassies) network.
