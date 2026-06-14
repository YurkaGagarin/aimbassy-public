# One-week development plan (solo)

> Covers: "the plan — which nodes to start with (the critical ones), which to defer, to make it in a week with Claude Code Opus 4.8."
> Principle: first the graded core (Ring A), then the showcase (B), then the dream (C) — on paper only.

## The golden rule of the week
**Every day must end with something that works end-to-end.** A "crooked but whole" bot on day 2, which you then improve, is better than a perfect chunking with no answer on day 5. This is straight from the methodology: "Just get something working. Start with strong models & simple prompts."

And one more: **writing the report and collecting material for the pitch — not on the last day, but in parallel every day** (15 minutes in the evening: what you did, what numbers, what screenshot). Otherwise the "Implementation" section (50%) and the pitch (10%) will be written in a panic.

---

## Priority map (what's critical vs what to defer)

| Node from your diagram | Ring | When | Why so |
|---|---|---|---|
| **RAG (prep→chunk→embed→retrieve→generate)** | A | Days 1-3 | This is 50% of the grade. The heart. |
| **Evaluation harness + metrics** | A | Day 3-4 | Without numbers the project is "unproven." |
| **One improvement + before/after table** | A | Day 4 | A direct methodology requirement. |
| **Demo interface (Streamlit)** | A | Day 2 (draft) | So there's something to show live from the start. |
| **Guardrail (DLP + Flash topic)** | B | Day 5 | Raises architecture and ethics. |
| **Router → human-handoff** | B | Day 5 | Closes the legal risk, the "fallback." |
| **Telegram bot + Cloud Run deploy** | B | Day 6 | Your "live bot" goal. A thin wrapper over the ready core. |
| **BigQuery (long-term + guardrail events)** | B | Day 6 | Storage + analytics for slides. |
| **Rate-limit (simple counter)** | B | Day 6 | Budget protection, without an LLM. |
| Escalating bans | C | — | Describe in the architecture. Don't code. |
| Interactive clarifications (loop) | C | — | Describe. Add if time remains. |
| ReAct agent + web search | C | — | Describe as a "next step based on eval results." |
| Lithuania (second country) | C | — | Design is ready (country filter); wait for data. |
| Court decisions | C | — | Scope-out; a NotebookLM prompt for the future. |

---

## Day-by-day plan

### Day 1 — Data foundation + GCP
Goal by evening: chunks with metadata sit in Chroma, search returns something.
- Set up the GCP project, enable Vertex AI, check the Gemini and embeddings quota (if not yet — this is the first thing, without it everything stalls).
- Pull the laws from RIS (HTML→MD) — cleaner than parsing PDF. Cases docx→MD via pandoc.
- Set metadata (`country, doc_type, law_code, paragraph, lang, source_url`).
- Structural chunking by § + overlap. Eyeball ~10 chunks.
- Embedding (gemini-embedding-001, dim 768, correct task_type) → Chroma.
- Smoke test: ask a question, look at whether the found pieces are relevant.

### Day 2 — First end-to-end answer + demo panel
Goal by evening: "question → answer with a reference to the §" works, visible in Streamlit.
- LangGraph graph: `retrieve → generate` (linear for now, no guardrail).
- System prompt (grounding + citation + disclaimer) + 2-3 few-shots in the style of the references.
- Streamlit panel: a question field, the answer, a display of the found chunks and sources (this is your "debug X-ray panel" — you'll see what's actually retrieved).
- This is already a demonstrable baseline.

### Day 3 — Evaluation harness (this makes the project "scientific")
Goal by evening: a table with baseline metrics on the 13 questions.
- Script: run the 13 questions through the pipeline, collect answers and found contexts.
- Metrics: retrieval (Hit Rate@k, MRR) + answer quality (RAGAS faithfulness/correctness OR your own Gemini-judge with a rubric).
- Expand the test set with synthetics to ~30-50 (separate from the 13 human ones).
- Lock in the baseline numbers. This is the reference point.

### Day 4 — Analysis + one improvement (the project's story)
Goal by evening: a "before/after" table with a gain in a metric.
- Understand from the metrics: is search to blame or generation?
- Pick 1-2 levers for the weak spot: contextual retrieval / hybrid (dense+BM25) / reranker / HyDE / Flash-vs-Pro on cost.
- Run the eval again, make the before/after table. Write the conclusion in words.
- This is your main slide and paragraph in the report.

### Day 5 — Guardrail + Router (safety and fallback)
Goal by evening: off-topic/PII are cut off, unconfident answers go to a "human."
- Guardrail node: Google DLP (PII) + Gemini Flash (topic/injection) → a structured verdict. The original is not saved.
- A mini-eval of the guardrail on ~40 labeled examples → a confusion matrix (here Accuracy/Precision/Recall/F1 are appropriate).
- Router after generation: a Flash-judge of confidence → below the threshold → text with the coordinator's contact + the sanitized question.

### Day 6 — Telegram + GCP prod (the showcase)
Goal by evening: a live bot answers in Telegram.
- `python-telegram-bot`: locally polling. Connect the ready LangGraph graph.
- BigQuery: tables `interactions` and `guardrail_events` (without originals). Write events there.
- A simple rate-limit (a counter; for the POC, in-memory/Firestore is fine).
- Deploy to Cloud Run (webhook). Verify end-to-end from a phone.
- If the deploy gets stuck — leave local polling + a video demo; it's not worth a lost day.

### Day 7 — Report, pitch, backup
- Finish the report (structure = the assignment sections: problem, research, architecture, implementation, KPI).
- Slides (8 min): hook → problem → solution → architecture (your diagram) → evaluation (before/after table) → demo (a video!) → impact → next steps.
- **Record a video demo for sure** (methodology: "live demo? make sure you have a video as backup").
- Final architecture diagram (draw the `01` diagram cleanly).

---

## If time gets tight — the order of "what to cut"
Cut from the end of the priority list, never from Ring A:
1. First sacrifice the Cloud Run deploy (keep the local bot + a video).
2. Then Telegram (keep the Streamlit demo).
3. Then BigQuery (keep CSV logs).
4. Simplify the Router and Guardrail to a single prompt.
**The core (RAG + eval + one improvement) is never cut.** A perfect core without Telegram is better than Telegram without a measured RAG.

---

## How to work effectively with Claude Code (Opus 4.8) — practice

You will write the code with my hands. To make this fast and chaos-free:

1. **Break tasks into nodes.** Not "build me a RAG," but "build a chunking module: input — a folder of MD, output — a list of chunks with metadata, cut by §, overlap 15%." One node = one clear input/output. This keeps the code cleaner and makes me err less.
2. **Test/criterion first, then code.** Say "here are 3 questions, the answer must contain a § and not invent" — and I'll be able to check myself.
3. **Keep a `CONTEXT.md` in the repo** with the current state (what's done, what the eval numbers are, what's next). After long sessions I'll be able to recover quickly.
4. **Commit working versions (git commit) often.** Being able to roll back to a working state matters more than beauty.
5. **Be careful with the .venv on the Desktop.** You already had recurring venv corruption from iCloud sync on the Desktop. Keep the venv OUTSIDE the synced folder (e.g., `~/venvs/ambassy`) or use a container. This will save you hours.
6. **Parallel models for development.** You have Claude Code, Codex, Gemini CLI. Codex/Gemini are good for a second opinion on a hard bug or for generating synthetic test questions in batches. But one "repo owner" (me) — so there are no edit conflicts.
7. **Secrets — in environment variables / Secret Manager, not in code.** The Telegram token, GCP keys. And `.gitignore` for them (the repo is public on GitHub per the assignment).

---

## Definition of Done for grading (hang it in front of your eyes)
- [ ] RAG answers a question with a § citation and a disclaimer.
- [ ] There's a table of baseline and "after improvement" metrics with a delta.
- [ ] A demo works (Telegram or Streamlit) + a video is recorded.
- [ ] A clean architecture diagram.
- [ ] A report by the assignment sections + a public GitHub repo.
- [ ] Slides for 8 minutes with numbers and a story.

Next — `05` (NotebookLM prompts) and `06` (mentor/teacher questions).
