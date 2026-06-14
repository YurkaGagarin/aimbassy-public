# RAG: design bone by bone

> This is the heart of the project (50% of the grade). Covers: "RAG techniques and technologies — file preparation, chunking, embedding, retrieval" + proper evaluation.
> The order of sections = the order of development.

## First — how RAG works at all (in plain terms)

RAG = "Retrieval-Augmented Generation" — "generation with a peek into the textbook." Everyday analogy: a student at an open-book exam. Without RAG, the model answers "from memory" (and may invent everything — a hallucination). With RAG, we first find the needed textbook pages (retrieval), put them in front of the model, and say "answer ONLY from these pages" (generation). For a legal bot this is critical: the cost of an invented law is real harm to a person.

The pipeline: **file preparation → cutting into chunks (chunking) → turning chunks into vectors (embedding) → storage (vector store) → finding the needed chunks (retrieval) → generating the answer → evaluation.**

---

## Stage 1. File preparation (data preparation)

Goal: turn motley PDF/RTF/DOCX into clean structured text with metadata. RAG is not smarter than its documents — garbage in = garbage out.

### What we do
1. **Conversion to Markdown while preserving structure.** Legal text rests on the hierarchy `§ → Absatz (paragraph) → Ziffer (item)`. This structure must be preserved — it will be the chunk boundaries and the source of citations.
2. **Cleaning.** Remove headers/footers, page numbers, "Fassung vom…", watermarks, repeating headings — this is noise that confuses search.
3. **Metadata tagging** at the document level (later inherited by chunks).

### Tools (choice → why → alternatives)
- **Choice: LlamaParse or Docling for PDF→MD.** Why: both are tuned to extract structure (headings, lists, tables) from "dirty" PDFs better than plain `pypdf`. Docling is open-source (free, local). LlamaParse is cloud-based, very strong on complex layouts (has a free tier).
  - *Alternative — pypdf/pdfplumber.* Plus: free, simple. Minus: loses structure, glues columns together. Weak for laws.
  - *Alternative — Gemini as a parser (multimodal: feed PDF pages and ask for structured MD).* Plus: understands layout and language excellently. Minus: more expensive, slower on large files. Good for "hard" pages.
  - *RTF/DOCX:* `pandoc` (rtf/docx→md) — fast and free. Your laws are duplicated in RTF — take the RTF via pandoc, it's simpler than PDF.
- **Source of truth — the official RIS site (ris.bka.gv.at).** `Sources.xlsx` has links. It's better to pull the current law text from RIS (clean HTML) than to parse PDF. HTML→MD is trivial and preserves the § structure. This will save a lot of time.

### Metadata (this is your two-stage advantage)
For each document/chunk:
```yaml
country: AT              # key for the first filtering stage
doc_type: law            # law | case | court_decision
law_code: NAG            # NAG | FPG | StbG | null
paragraph: "§ 88"        # for citation
lang: de                 # de | ru
source_url: "https://ris.bka.gv.at/..."
title: "Niederlassungs- und Aufenthaltsgesetz"
last_updated: "2026-05-18"
```
Why: (1) a filter by `country` BEFORE the vector search (quickly and accurately narrows it down); (2) `paragraph`+`source_url` → the answer cites the source ("according to § 88 FPG, …") = trust + verifiability + a direct answer to the methodology's "quote the source" requirement.

---

## Stage 2. Chunking (cutting)

This is the most underrated stage — quality depends on it more than on the choice of model. Goal: chunks must be "complete thoughts," not torn, and not too large.

### Strategy (choice → why → alternatives)
- **Choice: structural chunking by § with overlap.** Cut by paragraph/sub-paragraph boundaries (not by blind N characters), so that each chunk = a whole legal norm. If a § is long — cut by paragraphs with overlap.
  - Why: a lawyer answers "per § 88," not "per a random 500 characters." A whole § = a whole answer.
- **Size.** Aim for ~300-600 tokens per chunk (remember the embedding limit of 2048 tokens — with margin). Don't push to the limit: small precise chunks search better than large ones.
- **Overlap ~10-15%.** Why: so that a thought at the seam of two chunks isn't lost. Analogy: you cut a long sausage, but each next slice slightly "overlaps" the previous one, so you don't lose what was exactly at the cut.

**Alternatives:**
- *Fixed-size (by N characters).* Plus: trivial. Minus: tears norms in the middle. Only as a baseline.
- *Recursive character splitting (LangChain).* Plus: respects paragraphs/sentences, a reasonable default. Minus: doesn't know about §. Good as a starting point, then improve to structural.
- *Semantic chunking (cut where meaning changes).* Plus: "smart" boundaries. Minus: more expensive (needs embeddings during cutting), unstable. Overkill for a POC.

### Contextual Retrieval (what you called "data enhancement") — do it for sure
This is an Anthropic technique, very effective and simple. Before embedding, we **prepend 1-2 sentences of context** to each chunk, generated by an LLM: "This fragment from the NAG law, § X, describes the conditions for extending a residence permit for…".

Why (analogy): imagine an encyclopedia card with no title — "…no more than 6 months." About what? Unclear. But with context — "Asylum review period: no more than 6 months for the initial decision." Now the card is found by meaning. Contextual retrieval especially saves you on cross-lingual: a Russian question latches onto a chunk that has a meaningful description.

How to do it cheaply: run each chunk through Gemini Flash once at indexing time (this is offline, one-off). Save "context + chunk" as the text to embed, and return the original chunk to the user.

---

## Stage 3. Embedding

- **Model: `gemini-embedding-001`** (justification — in `02`: top multilingual, RU incl., Matryoshka).
- **What we embed:** `context (from contextual retrieval) + chunk text`. Not the bare chunk.
- **Dimension:** start with 768 (fast, cheap, on a small corpus quality is almost like 3072). If precision is lacking — raise to 1536/3072.
- **task_type:** Gemini embeddings have task types — use `RETRIEVAL_DOCUMENT` for chunks and `RETRIEVAL_QUERY` for the query (these are different "modes," noticeably affecting search quality — a common beginner mistake is using one type for both).

Cross-lingual nuance: a multilingual embedding places "a Russian question about a residence permit" and "a German § about an Aufenthaltstitel" close together in one space — that is the bridge across languages. But it's not perfect. So in `02` we added enrich/query translation into German as insurance for recall.

---

## Stage 4. Retrieval (search)

Two-stage, as you intended.

**Stage 1 — filter by metadata.** `WHERE country = 'AT'` (and optionally `doc_type`). This is not a vector but an ordinary filter — instantly cuts off what's foreign. When Lithuania is added, the same system works without changes (just a different `country`). This is your "scalability" slide.

**Stage 2 — hybrid search within the filtered set:**
- *Dense* (vector, by meaning) — catches paraphrases and cross-lingual.
- *Sparse* (BM25/keywords) — catches exact markers: "§88", "NAG", "Blaue Karte", period numbers.
- Combine via **RRF (Reciprocal Rank Fusion)** or a weighted sum. Tune the weights on the eval set (you anticipated this yourself — correctly).

Why hybrid (analogy): dense is "find by meaning what it's about," sparse is "find the exact word." The legal query "what does §88 say about an alien's passport" needs both: meaning (an alien's passport) + the exact marker (§88).

**Stage 3 — Reranking.** Take the top 15-20 candidates → the Vertex Ranking API returns the top-5 by relevance. Cheap, a noticeable precision gain.

**How many to feed into generation (top-k):** start with k=5. More context ≠ better: extra pieces dilute the model's attention and raise cost/latency.

**Alternatives for retrieval:**
- *Dense only.* Simpler, but loses exact §/numbers. A baseline.
- *Parent-document retrieval* (search by small chunks, return the whole parent §). Plus: precise search + full context in the answer. Minus: slightly more complex storage. A strong upgrade if answers come out fragmentary.
- *No rerank.* Faster, cheaper, lower precision.

---

## Stage 5. Generation (answer generation)

The system prompt must contain:
1. Role: "You are an assistant on immigration and legalization matters in {country}. You answer in the language of the question (RU/BY)."
2. A hard grounding rule: "Answer ONLY based on the provided fragments. If the answer is not in them — honestly say there is not enough information, and do not invent."
3. A citation requirement: "Indicate the source: the law and the § (e.g., § 88 FPG) and a link."
4. A disclaimer: "This is not legal advice; for decisions consult a lawyer/coordinator."
5. Few-shots in the style of your 13 reference answers (short, to the point, with a reference).

This turns a "chatty model" into a "cautious legal clerk."

---

## Stage 6. EVALUATION — read carefully, this was the confusion in the PRD

Recall the conclusion from `00`: **a Confusion Matrix ≠ a quality metric for a free-text answer.** Let's lay out what to measure with what. You essentially have THREE different things to evaluate, and each has its own metrics.

### A) Guardrail classifier → here the Confusion Matrix is appropriate
The task "on-topic / off-topic," "has PII / no PII" is classification (yes/no). You label ~40-60 examples (some are real immigration questions, some are junk/off-topic/injections/with PII), run the guardrail, and build:
- **Accuracy** — the share of correct verdicts.
- **Precision** — of those marked "off-topic," how many really are off-topic (so you don't block living people for nothing).
- **Recall** — of all the real off-topics/PII, how many you caught (so you don't miss a PII leak).
- **F1** — the balance. For PII, Recall matters more (missing a leak is worse than being over-cautious).
Tool: `sklearn.metrics` (`classification_report`, `confusion_matrix`). This is exactly where your KPIs from the PRD go.

### B) Retrieval → search metrics (also partly "confusion-like")
The question: "did we find the needed chunk among the top-k?". For each test question you label in advance which §/document contains the answer (the ground-truth chunk). Then:
- **Hit Rate / Recall@k** — in what share of cases the needed chunk landed in the top-k.
- **MRR / nDCG** — how high it stands in the ranking.
- **Context Precision / Context Recall** (RAGAS) — relevance of the found context.
This shows whether SEARCH or GENERATION is to blame for a bad answer. Invaluable for debugging.

### C) RAG answer quality → LLM-as-judge (RAGAS), NOT a confusion matrix
Compare free text to a reference via a judge model. Key RAGAS metrics:
- **Faithfulness** — the answer relies on the context, not invented (anti-hallucination). For a legal bot — metric #1.
- **Answer Correctness / Semantic Similarity** — does it match Anastasia's reference answer in meaning.
- **Answer Relevancy** — does it answer the asked question (rather than talking around it).
Tool: **RAGAS** (can work with Gemini as judge and as embeddings). Alternative — your own prompt-judge on Gemini Pro with a 1-5 rubric (simpler, more transparent for the report; show the rubric in the appendix).

> Mentor's advice on the judge: judge with a model OTHER than the one that generated (conflict of interest). Generate with Flash → judge with Pro, or vice versa. And always show 2-3 examples of manual verification that the judge is adequate (the instructor will ask "can we trust the judge?").

### How to tie this to the assignment's KPI table
In the assignment, Technical KPIs: Accuracy 90%, Latency <2s, Error rate <5%. Mapping:
- "Accuracy 90%" → your **Answer Correctness** (RAGAS/judge) on 13+synthetics. Be honest: 90% on legal questions is ambitious; lock in a baseline and an improvement. "Documented failure > fudged success."
- "Latency <2s" → measure end-to-end time. With retrieval+rerank+Pro, 3-6s is realistic; that's fine, describe the trade-off (quality vs speed) and show that Flash comes closer to the goal.
- "Error rate <5%" → the share of answers with faithfulness below the threshold (hallucinations) OR those that went to fallback.

### The evaluation working cycle (this is your "story" for the pitch)
1. **Baseline:** the simplest RAG (fixed chunking, dense-only, k=5, Gemini Pro, no enrich/rerank). A run on the 13 questions. Record all three metric groups.
2. **Analysis:** where does it break down — retrieval (doesn't find) or generation (finds, but answers poorly)? Metrics B vs C give the answer.
3. **Improvement (pick 1-2 levers):** contextual retrieval, hybrid, reranker, HyDE, or Flash-vs-Pro on cost. Run again.
4. **A "before/after" table** with the delta per metric. This is exactly what the instructor wants to see.

---

## Checklist of the RAG development order (tick the boxes)
- [ ] Pull the laws from RIS (HTML) → MD; cases docx→MD (pandoc). Metadata set.
- [ ] Structural chunking by § + overlap. Eyeball 10 chunks — are they torn?
- [ ] Contextual retrieval: prepend context to chunks (Flash, offline).
- [ ] Embedding (gemini-embedding-001, 768, correct task_type) → Chroma.
- [ ] Retrieval baseline (dense, k=5) → assemble the first end-to-end answer.
- [ ] Eval harness: 13 questions → metrics A/B/C. This is your baseline.
- [ ] Improvement (hybrid + rerank OR contextual OR enrich) → repeat eval → before/after table.

Next — `04`, the week plan by days.
