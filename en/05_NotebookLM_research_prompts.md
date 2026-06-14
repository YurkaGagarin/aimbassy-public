# Deep-research prompts (NotebookLM)

> Covers: "preparing prompts for deep research in NotebookLM."

## How to use this (important about NotebookLM)
NotebookLM answers ONLY based on the sources you load into it (PDF, links, Google Docs, YouTube). It does not search the open internet by itself. So the strategy is twofold:
1. **Collecting sources.** First find and load the documents (via ordinary search/Gemini with web search, by the links in `Sources.xlsx`, the RIS, EUAA, BVwG sites).
2. **Interrogating the sources.** Then ask NotebookLM the prompts below — it synthesizes, cites, and does not invent.

To find the sources themselves (where to get court decisions, etc.), use the prompts from section C in Gemini/Perplexity with web search, and load what you find into NotebookLM.

The prompts are grouped: A — mapping the legal field, B — populating RAG content, C — finding court decisions (your separate task), D — generating test questions.

---

## A. Mapping the legal field (for the "Market & Technical Discovery" section, 15%)

**A1. Structure of Austrian immigration law for refugees from Belarus**
```
You are an expert in Austrian migration law. Based on the loaded sources, compile a structured map of the legal field for a Belarusian citizen seeking asylum or legalization in Austria. Split by topics: (1) applying for asylum (Asyl), (2) types of residence permit (Aufenthaltstitel), (3) citizenship (Staatsbürgerschaft), (4) the right to work, (5) family reunification. For each topic indicate: the key laws and paragraphs (NAG, FPG, AsylG, StbG), the responsible authorities, typical timelines, typical grounds for refusal. Everywhere give an exact reference to the source and paragraph. Where sources diverge or information is outdated — note this explicitly.
```

**A2. Glossary of terms (RU ↔ DE) — critical for cross-lingual RAG**
```
Compile a bilingual glossary (Russian — German) of key legal terms from the loaded documents on the topic of asylum and legalization in Austria. For each term: the German original, the Russian translation, a brief explanation in plain language, and the paragraph/law where it is defined. Include the terms: Aufenthaltstitel, Niederlassungsbewilligung, Rot-Weiß-Rot Karte, subsidiärer Schutz, Asylberechtigter, Aufenthaltsberechtigung, Niederlassungsnachweis, Fremdenpolizei. Output as a table.
```
> Later load this glossary into your RAG as a separate document — it will directly improve cross-lingual retrieval.

---

## B. Populating and enriching RAG content

**B1. Compressing a law into a FAQ format (for contextual retrieval and few-shots)**
```
Based on the loaded law text [NAG / FPG / StbG], formulate 15 pairs of "refugee question — exact answer." The questions in plain language, as an ordinary person would ask (in Russian). The answers strictly from the law text, with a mandatory reference to the specific paragraph (§) and without making things up. If the law gives no direct answer — say so. Format: Question / Answer / § source.
```

**B2. Contextual annotations to sections (for contextual retrieval)**
```
For each paragraph of the loaded law, write a one-sentence annotation in Russian: what this paragraph is about and in what life situation it applies. Format: "§ X — [annotation]". This is needed as metadata for the search system.
```

---

## C. Finding court decisions (your separate task — where to get precedents)
> These prompts are for Gemini/Perplexity with web search, to FIND sources. Load what you find into NotebookLM.

**C1. Where to look for Austrian court decisions on migration**
```
Find official and free databases of Austrian court decisions on migration and asylum cases. I am interested in: Bundesverwaltungsgericht (BVwG), Verwaltungsgerichtshof (VwGH), Verfassungsgerichtshof (VfGH). For each source indicate: the URL, how to filter by the topic "asylum/Asyl" and "Belarusian citizenship," whether the full text of decisions is available, whether there's an API or export, the language. Also check the RIS databases (ris.bka.gv.at) and the EUAA Case Law Database. Give direct links to the filtering sections.
```

**C2. Relevant precedents for Belarusians**
```
Find and briefly summarize publicly available Austrian court decisions (BVwG/VwGH) on asylum cases of Belarusian citizens for 2020-2026. For each: the case number, date, essence, outcome, the key legal argument, a link to the full text. Note which ones can be downloaded in full for further analysis.
```

---

## D. Generating test questions for evaluation (expanding the golden set)

**D1. Synthetic test questions from the corpus**
```
Based ONLY on the loaded documents, generate 40 test pairs "question — reference answer" for evaluating a legal assistant. Requirements: realistic questions, in Russian, of varying difficulty (simple factual, multi-step, edge cases). Each reference answer is strictly from the source, with the § and law indicated. Add 5 "trap questions" that have NO answer in the documents (the correct system reaction is to honestly say "not enough information"). Table format: Question | Reference answer | Source(§) | Type | Has_answer(yes/no).
```
> "Trap questions" are gold: they check whether the bot hallucinates. The instructor will appreciate this.

**D2. Questions on cross-lingual robustness**
```
Translate the following 13 Russian test questions into Belarusian, preserving the legal meaning. The goal is to check whether the system answers equally well in Russian and Belarusian. Output a table: Russian | Belarusian.
```

---

## What NOT to do with NotebookLM
- Don't ask it to "find on the internet" — it works by loaded sources.
- Don't trust an answer without a reference — always require a source citation (it can do this).
- Don't load people's personal data into it.

Next — `06`, questions for the mentor and the teacher.
