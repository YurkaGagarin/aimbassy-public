# Technology stack per node

> Covers the request: "stack selection per node + why + alternatives with pros/cons".
> Context: runtime — Google/Vertex (your choice), models current as of June 2026.

First — a quick "what to take" cheat sheet, then a breakdown per node with alternatives.

## Summary table (this can be pasted almost verbatim into section 3 of the report)

| Component | Choice | Why (brief) |
|---|---|---|
| Flow orchestration | LangGraph | You already know it from HW-3; gives a node graph, state, checkpointer = your "flow state memory" for free. |
| Interface | Telegram (python-telegram-bot) on Cloud Run (webhook) | Your goal is a live bot; webhook on Cloud Run = serverless, pay per call. |
| Rate-limit / destructive | Counter in BigQuery or in-memory; prefilter Gemini 3.1 Flash-Lite | Budget protection without an LLM; cheap topic prefilter before expensive generation. |
| Guardrail: PII | Google Cloud DLP API | A specialized tool for PII, no need to reinvent regex/LLM. |
| Guardrail: topic/injection | Gemini 3.5 Flash (classification) | Cheap, fast, multilingual; one call = on-topic? injection? |
| Query enrich | Gemini 3.5 Flash | RU/BY→DE translation + term expansion in one cheap call. |
| Embeddings | gemini-embedding-001 (Vertex) | Top MTEB multilingual, 100+ languages (RU incl.), Matryoshka 768/1536/3072. |
| Vector store (POC) | ChromaDB locally (or FAISS) | Zero infrastructure, instant start for iterations. |
| Vector store (prod) | BigQuery Vector Search OR Vertex Vector Search | BQ — a single data platform (you already keep abuse/long-term there); Vertex — for scale. |
| Reranker | Vertex AI Ranking API (semantic-ranker) | Raises retrieval precision — a cheap "improve one dimension" lever. |
| LLM (main "brain") | Gemini 3.5 Pro (baseline), then Gemini 3.5 Flash for cost | "Start with the strongest" → then measure whether you can make it cheaper. |
| Router (after LLM) | Gemini 3.5 Flash as an LLM-judge | Evaluates the answer's confidence/grounding; below threshold → human. |
| Guardrail DB / Long-term | BigQuery | Already in your stack; SQL analytics for the report/metrics out of the box. |
| Evaluation | RAGAS + sklearn (confusion matrix for classifiers) | RAGAS for answer quality, sklearn for guardrail/retrieval. |

> Important for the report: the assignment table has a "Reason" column. Fill it with ONE benefit phrase (as above). Keep alternatives and trade-offs in the text/appendix — the instructor separately values "Trade-offs: what compromise did you make."

---

## Breakdown per node (choice → why → alternatives)

### Node 1. Orchestration — LangGraph

**Why.** You already covered it in HW-3, no time spent on a new framework. LangGraph gives three needed things: (1) a node graph = your diagram one-to-one; (2) typed state between nodes = your "flow state memory"; (3) a checkpointer = saving state at each step, which covers the "save state at every node" requirement almost for free.

**Alternatives:**
- *Pure Python script without a framework.* Plus: zero abstractions, simpler for a linear pipeline. Minus: you write state, branching (router), and persistence yourself. For linear RAG it's acceptable, but a graph looks more professional in the pitch.
- *Vertex AI Agent Engine / ADK (Google).* Plus: "all in Google," managed agent deployment. Minus: a new-to-you API in a week = risk; less control; vendor lock-in. Not now.
- *LlamaIndex.* Plus: a very fast start specifically for RAG (ready loaders, pipeline). Minus: yet another framework to learn; LangGraph is closer to you. You can use individual LlamaIndex pieces (parsers) inside LangGraph.

**Verdict:** LangGraph as the backbone. It's your "familiar home."

---

### Node 2. Interface — Telegram on Cloud Run

**Why.** The goal is a live bot. `python-telegram-bot` is a mature library. **Webhook** mode (rather than polling) deploys as an HTTP service on Cloud Run: serverless, scales to zero, pay per call — ideal for a demo and for "production mindset" in the pitch.

**Backup interface alternative:** **Streamlit**. Plus: stands up in an hour, convenient for showing metrics/sources on screen, great for a video demo. Minus: it's not a "real channel" for a refugee. **Mentor's advice:** build Streamlit FIRST (as a RAG debug panel in Ring A), and Telegram on top of the ready core in Ring B. If you don't finish Telegram — you still have a working demo.

**Polling vs webhook:** for local development, polling is simpler (no public URL needed). For prod on Cloud Run — webhook. Start with local polling, switch to webhook when deploying.

---

### Node 3. Destructive checks — rate-limit + cheap prefilter

**Why (two different tasks under one name):**
1. *Protection from a flood of messages* — this is infrastructure. A counter "N messages per T seconds by `telegram_id`." Storage: an in-memory dict for the POC; BigQuery/Firestore/Redis for prod. No LLM needed here.
2. *Budget protection from off-topic queries* — a cheap classifier `Gemini 3.1 Flash-Lite` BEFORE expensive Pro. It cuts off "write me code / draw a picture" for a fraction of a cent.

**Alternatives for rate-limit:**
- *Firestore* — plus: realtime, simple atomic counters, serverless. Minus: yet another service.
- *Redis (Memorystore)* — plus: classic rate-limit, fast. Minus: costs money even when idle, overkill for a POC.
- *BigQuery* — plus: already in the stack, everything in one place for analytics. Minus: BQ is not for frequent small real-time writes/reads (it is analytical, not transactional). **Nuance:** for counters Firestore is better, and BigQuery is for post-analysis of events. Say this honestly in trade-offs.

**Escalating bans:** describe them in the architecture (a user state table, a ban counter, a growing duration). Don't build them over a week — it's business logic without GenAI value for the grade.

---

### Node 4. Guardrails — DLP (PII) + Gemini Flash (topic/injection)

These are two sub-checks. Split them — different tools.

**4a. PII redaction — Google Cloud DLP API.**
Why: DLP is Google's specialized service for finding and masking personal data (names, phones, emails, passports, addresses) across 100+ types, with support for many languages. This is "the right tool for the right job." Everyday analogy: to find all passports in a stack of papers, you hire a trained clerk (DLP), not ask a poet (LLM) to "see if there's anything personal here."
- *Alternative — regex.* Plus: free, fast. Minus: breaks on variability (phones in different formats, names). Only as a coarse net.
- *Alternative — LLM (Gemini) for PII.* Plus: understands context ("my name is…"). Minus: can be subjected to injection, non-deterministic, more expensive. **Best solution:** DLP as the main layer + an LLM as an additional one for contextual cases.

**4b. Topic check and prompt-injection — Gemini 3.5 Flash.**
One call returns a structured verdict: `{on_topic: bool, category: str, injection_suspected: bool}`. Flash is cheap and multilingual (understands both Russian and Belarusian).
- *Alternative — Vertex AI safety filters / Model Armor.* Google provides built-in safety filters and Model Armor for protection against injections/jailbreaks. Plus: managed, no prompt to write. Minus: it filters "harm," but not "is this about immigration" — the topic check is still yours. **Advice:** enable Vertex's built-in safety filters as a lower layer + your Flash topic classifier on top.
- *Alternative — a separate guard model (e.g., ShieldGemma).* Plus: tuned for safety. Minus: yet another model in the infrastructure. For a POC, Flash + built-in filters is enough.

> Architectural rule (repeat it in the report): the original message is written NOWHERE. The guardrail outputs only the sanitized text; the raw query lives in the request's RAM and dies with it. Only the following go to the log/BigQuery: the fact of the event, the category, the sanitized text, the timestamp, and a `telegram_id` hash.

---

### Node 5. Query enrich — Gemini 3.5 Flash

**Why.** One cheap call builds the cross-lingual bridge: it rewrites the Russian/Belarusian question into (a) a normalized phrasing, (b) a translation/key terms in German (to hit the German laws), (c) an expansion with synonyms. This directly raises retrieval recall when languages diverge.

**Alternatives:**
- *HyDE (Hypothetical Document Embeddings).* The model generates a "hypothetical ideal answer," and we search by it. Plus: often greatly boosts retrieval. Minus: +1 generation (latency/cost). An excellent candidate for "improve one dimension."
- *Multi-query expansion.* You generate 3-4 reformulations, search by all, merge. Plus: catches different phrasings. Minus: more expensive, dedup needed. Also an improvement lever.
- *No enrich, rely on a multilingual embedding.* Plus: simpler, lower latency. Minus: on the RU↔DE gap recall will drop. **Advice:** build a baseline WITHOUT enrich (as the methodology dictates — the simplest), measure, then add enrich/HyDE and show the gain. This is your improvement story.

---

### Node 6. Embeddings — gemini-embedding-001

**Why.** As of June 2026 this is top MTEB multilingual, 100+ languages (Russian confidently, Belarusian partially), input up to 2048 tokens, dimension 3072 with Matryoshka (can be truncated to 1536/768 without noticeable loss — saving memory/search speed). For cross-lingual RU↔DE it's a strong default, and it's "native" to Vertex.

**Alternatives:**
- *text-multilingual-embedding-002 (Vertex, older).* Plus: cheaper, proven. Minus: weaker on benchmarks. A fallback.
- *gemini-embedding-2 (multimodal).* Plus: text+images+audio. Minus: you don't need multimodality — extra complexity/cost.
- *Open-source BGE-M3 / multilingual-e5-large.* Plus: free, self-hostable, BGE-M3 is strong in cross-lingual and provides dense+sparse at once. Minus: you need to run it somewhere (GPU/CPU), you step away from the "Google stack." A good argument for a "how to cut cost" slide (drop the paid embeddings).

> Practical detail: embed not the "bare chunk," but "chunk + its contextual description + metadata" (contextual retrieval). And remember the 2048-token input limit — your chunks must be smaller. Details in `03`.

---

### Node 7. Vector store — Chroma (POC) → BigQuery/Vertex (prod)

**POC: ChromaDB (or FAISS).** Why: zero infrastructure, lives in a file/memory, instant iterations on chunking/embeddings. On a corpus of a few laws it flies. Analogy: while you're trying out a recipe — you cook in your own kitchen, you don't build a restaurant.

**Prod, option 1: BigQuery Vector Search.** Plus: you already keep the abuse-DB and long-term memory there — ONE data platform, unified SQL, cheap storage, metric analytics in the same place. Minus: search latency is higher than a specialized index; not for thousands of QPS. For your volumes — excellent and coherent in the pitch.

**Prod, option 2: Vertex AI Vector Search.** Plus: managed ANN index, low latency, scale. Minus: more expensive, harder setup (index/endpoint/deploy), overkill for a small corpus.

**Alternative: pgvector on Cloud SQL/AlloyDB.** Plus: familiar Postgres, metadata filtering + vector in one query, hybrid is convenient. Minus: managing a DB. A good middle path if you like SQL.

**Verdict:** Chroma for development, BigQuery Vector Search for the prod demo (stack coherence > peak performance at an educational volume).

---

### Node 8. Retrieval + Reranker

**Retrieval.** Two-stage (as you intended): (1) a hard filter by the `country` metadata (and optionally `doc_type`), (2) a hybrid search within: dense (embeddings, meaning) + sparse (BM25/keywords, exact terms and § numbers). Legal queries often contain exact markers ("§88", "NAG") — pure semantic search loses them, hence the hybrid.

**Reranker — Vertex AI Ranking API.** After the hybrid you take the top-20 candidates and rerank them with a ranker model into the top-5. This is a cheap and strong precision lever. Analogy: first a coarse sieve (quickly pull 20 plausible ones), then an expert taster (the ranker) picks the best 5.
- *Alternative — Cohere Rerank multilingual.* Plus: very strong, multilingual. Minus: outside the Google stack.
- *Alternative — no ranker.* Simpler/faster, but lower precision. **Advice:** baseline without a ranker → add a ranker → show the gain (again "improve one dimension").

---

### Node 9. LLM "brain" — Gemini 3.5 Pro → Flash

**Why exactly this way.** The methodology dictates: "start with the strongest model." The strongest in the lineup is `Gemini 3.5 Pro` (the flagship; if unavailable by quota — `gemini-3.1-pro-preview`). You build the baseline on Pro, lock in the quality. Then you try `Gemini 3.5 Flash`: if quality dropped insignificantly while cost/latency fell several-fold — that's your ready "improve cost dimension" story.

**Alternatives (for a comparison slide):**
- *Claude / GPT* — often stronger at reasoning and instruction-following. Minus: outside the Google stack, separate billing. You can mention them as "we considered them, chose Gemini for a unified ecosystem and credits" — that's a valid trade-off.
- *Gemini 3.1 Flash-Lite* — for the cheapest sub-nodes (guardrail/router/enrich), not for final generation.

> For generation, mandatory: (1) a system prompt with the role "legal immigration assistant for country X," (2) few-shots in the style of your reference answers, (3) a requirement to cite the § and source, (4) a disclaimer "does not replace a lawyer," (5) the instruction "if the context has no answer — say so honestly, don't invent" (anti-hallucination).

---

### Node 10. Router after the LLM — Gemini Flash as judge

**Why.** After generation, a second cheap call evaluates the answer: is it in the sources (grounding), is it confident, is it complete. Below the threshold → we hand over the coordinator's contact + the sanitized question to them. This covers "fallback for unanswered questions" and removes the legal risk.

**Alternatives:**
- *Confidence via logprobs/self-assessment of the generator.* Plus: no extra call. Minus: an LLM's self-assessment is unreliable. A judge by a separate model is more honest.
- *RAGAS faithfulness as a threshold.* Plus: a formal metric. Minus: computed offline, not in real time. Use RAGAS for the reporting evaluation, and the Flash-judge for runtime routing.

---

### Node 11. Storage — BigQuery (Guardrail DB + Long-term)

**Why BigQuery.** Already in your stack; serverless; SQL analytics out of the box — and for the report you need exactly the aggregates (how many queries, how many went to a human, top topics, how many guardrail triggers). One SELECT and you have numbers for slides.

**Schemas (minimum):**
- `guardrail_events`: `event_id, telegram_id_hash, category, sanitized_text, ts, action_taken`.
- `interactions`: `interaction_id, telegram_id_hash, sanitized_query, country, retrieved_sources[], answer, judge_score, routed_to_human(bool), ts`. **Without the original message.**

**Nuance (repeat in trade-offs):** BigQuery is analytical storage, not transactional. For frequent realtime counters (rate-limit, bans) Firestore is better; BigQuery is for logging and analytics. Don't build the rate-limit on BigQuery.

**Alternative — Firestore for everything operational** (user state, bans, counters) + BigQuery for analytics. This is the "correct" prod architecture: hot data in Firestore, cold data in BQ. You can describe it that way in the architecture and implement it minimally.

---

## Stack summary

One coherent "Google story" for the pitch: *LangGraph orchestrates the graph; Telegram on Cloud Run receives the request; Firestore/a counter dampens the flood; Gemini Flash + DLP clean and check; gemini-embedding-001 + BigQuery/Vertex Vector Search search the Austrian laws with a country filter and a reranker; Gemini Pro generates the answer with a § citation; a Gemini-judge decides whether to hand it to a human; BigQuery stores anonymized analytics.*

Next — `03`, where RAG is broken down bone by bone (this is your 50%).
