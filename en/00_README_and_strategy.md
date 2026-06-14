# [AI]mbassy — strategy and document map

> Mentor: Pyotr Georgievich. Date: 2026-06-08. Student: solo. Deadline: ~1 week.

This is the root document. It holds the overall verdict, the main scope recommendation, and the map of the other files. Read this one first.

---

## 1. Verdict in two paragraphs (verdict-first)

**The idea is strong, socially meaningful, and maps well onto the assignment's grading criteria.** You have something rare for a student project: a real problem, real data (Austrian laws + cases), and a ready-made golden test set with answers. That is gold for the Evaluation section, which instructors value above all else ("it works" without numbers does not count).

**But your PRD architecture is sized for a team of 3-4 people over a month, not for a solo developer in a week.** That is not a criticism — it is normal at the dreaming stage. My main job as a mentor: help you separate the "graded core" (what earns points and must work perfectly) from the "architecture showcase" (what you describe and diagram, but implement minimally or defer). If you try to do everything, you will finish nothing, and the block that weighs 50% is exactly the one that suffers.

---

## 2. How grading works (this dictates everything else)

From the assignment file, percentages of the final grade:

| Section | Weight | What they actually check |
|---|---|---|
| 1. Problem selection | 5% | Clear, measurable description of the pain. You already have it. |
| 2. Market research and technical discovery | 15% | Competitors, gaps, audience, data availability, feasibility. |
| 3. GenAI system architecture | 20% | Diagram + stack table with justification for each choice. |
| **4. Implementation** | **50%** | **A working POC + honest evaluation + improving at least one dimension.** |
| 5. Pitch to class | 10% | 8 minutes + 4 min Q&A. Story, demo, numbers. |

Key quotes from the methodology (Project Breakdown) that I will repeat like a mantra:

- "Start with the strongest model and the simplest possible prompt. Only optimize after you have a baseline."
- "Improve **at least one** dimension (latency / cost / quality / robustness). You don't need to improve everything."
- "Simplicity is fine: Clear, working > complex and fragile."
- "A well-documented failure is worth more than a fudged success."

Translated into plain terms: **you don't need an over-engineered system. You need one working core (a RAG answer to a legal question), measured by metrics, plus one meaningful improvement.** Everything else is a bonus and material for a "next steps" slide.

---

## 3. Main scope recommendation (read this twice)

You chose the goal "Telegram + full GCP prod." I accept it, but I repackage it into a safe sequence. Principle: **first what is graded, then what is pretty.**

Three priority rings:

**Ring A — THE GRADED CORE (must, ~60% of time).** Without it there is no project.
- RAG pipeline for Austria: file preparation → chunking → embeddings → retrieval → answer generation on Gemini.
- Evaluation on your 13 golden questions (+ expand with synthetic) using clear metrics.
- One documented improvement (e.g., Flash vs Pro on cost/quality, or +reranker for retrieval).
- A thin demo interface (Telegram bot OR Streamlit) — so there is something to show live.

**Ring B — THE PROD SHOWCASE (should, ~25% of time).** Raises the score for architecture and "production mindset."
- Deploy to Cloud Run (the bot as a webhook service).
- Guardrails as one node: PII redaction (Google DLP API) + topic check (Gemini Flash).
- Router after the LLM: an LLM-judge checks the answer's confidence, otherwise hands over the coordinator's contact.
- Storage in BigQuery (long-term + guardrail events).

**Ring C — THE ARCHITECTURE DREAM (could / describe but do NOT code this week, ~15% of time on description).**
- DDOS protection and an escalating ban system (this is infrastructure, not GenAI — describe it, don't build it).
- Interactive clarifying-question loop with state management.
- A full ReAct agent with web search.
- Two-country support (Lithuania) — no data yet, keep it as "design for scalability."

> If by the end of the week Ring A works and is measured — you already have a solid grade. Each Ring B element is a plus. Ring C is the "give me two more weeks and a budget" slide.

---

## 4. The most important technical turn you must understand

**You conflated two different types of metrics.** In the PRD you write that you will measure RAG quality via a Confusion Matrix (Accuracy / Precision / Recall / F1). This is a common and understandable mistake. Let's break it down with an everyday example.

- **A Confusion Matrix** works where the answer is "yes/no" or "class A/B/C." Everyday analogy: a covid test — it is either positive or negative, and we count how many times the test was wrong. That is about **classifiers**.
- **RAG answer quality** is free text ("About a quarter receive asylum, the statistics are declining..."). There is no "correct class" here. You cannot say "this paragraph is a false positive."

So the metrics split like this (details in `03_RAG_design.md`):

- Confusion Matrix (Accuracy/Precision/Recall/F1) is correctly applied to the **Guardrail classifier** ("query is on-topic / off-topic", "has PII / no PII") and to **retrieval** ("did we find the right document in top-k").
- RAG answer quality is measured via **LLM-as-judge** (RAGAS approach): *faithfulness* (the answer is not invented, it relies on the source), *answer correctness* (matches the reference in meaning), *context precision/recall* (relevance of retrieved chunks).

This is not nitpicking — it directly shapes how you build the evaluation table in your report. And it's an excellent question for the teacher (see `06`).

---

## 5. Map of the documents in this folder

| File | What's inside | Which of your requests it covers |
|---|---|---|
| `00_README_and_strategy.md` | This file: verdict, priority rings, metrics | Overall strategy |
| `01_Idea_materials_and_flow_review.md` | Idea evaluation, state of materials, critical review of your diagram + corrected diagram | "idea evaluation", "flow review and suggestions" |
| `02_Technology_stack.md` | Stack table per node: choice + why + alternatives (pros/cons) | "stack selection per node" |
| `03_RAG_design.md` | Deep dive on RAG: file preparation, chunking, embeddings, retrieval, evaluation | "RAG techniques and technologies" |
| `04_One_week_development_plan.md` | Day-by-day plan: what first, what to defer, how to work with Claude Code Opus | "development plan", "what's critical / what to defer" |
| `05_NotebookLM_research_prompts.md` | Ready-to-use prompts for deep research | "preparing prompts for NotebookLM" |
| `06_Mentor_and_teacher_questions.md` | Question sets: 1 hour for the mentor, 15 min for the teacher | "question set for mentor and teacher" |

---

## 6. What I need from you (open questions)

They don't block reading the documents, but they will affect the final plan. Answer whenever convenient:

1. Do you already have an enabled GCP project with billing and a Vertex (Gemini) quota? If not — that's half a day of setup, which must be accounted for.
2. What language should the bot answer in — always Russian, or in the language of the question?
3. Will the Lithuania materials realistically arrive in the next 2-3 days, or do we plan the demo on Austria only?
4. "Court decisions" is currently an empty folder. Is that deliberate (deferred), or are you expecting me to help with sources for court decisions?

Next — read `01`.
