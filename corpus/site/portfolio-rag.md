---
title: "Ask-about-Aditya — a glass-box RAG chatbot"
slug: "site-portfolio-rag"
kind: "portfolio"
site_slug: "portfolio-rag"
page_url: "https://adityamukhopadhyay.vercel.app/work/portfolio-rag"
source: "site/projects.ts"
themes: ["Retrieval & matching", "Safety & cost", "Pipelines"]
---
# Ask-about-Aditya — a glass-box RAG chatbot

The assistant on this site: hybrid retrieval over my own project documents, cited answers, and the whole pipeline visible per question — A/B-evaluated on a judged benchmark.

Period: 2026 · personal. Stack: Python, FastAPI, Qdrant, Gemini, SSE, Next.js, Railway, Vercel.

## Headline numbers

- **38** — documents · 290 sections indexed
- **98.9%** — ground-truth section in the final five
- **5** — configs A/B-tested, judged

## Context

Every portfolio claims things; this one lets you check. **Ask-about-Aditya** answers questions about my work from the same project documents behind this site, cites the passage each claim came from, and streams its own retrieval pipeline to the screen as it runs — the expanded queries, the dense and sparse top-K, the reciprocal-rank fusion, the reranker's reordering with a one-line reason per passage, and every model call with its latency.

The stack is deliberately plain and fully hosted: FastAPI and Qdrant on Railway over a private network, Gemini for embeddings, reranking and generation, and the front end in this Next.js site. Two chunking strategies were built and evaluated against each other before one was made the default.

## How it works

### Hybrid retrieval, fused where you can see it

Each unit carries a dense Gemini embedding (768-d, unit-normalised) and a BM25-style sparse vector written from scratch — hashed term ids, tf saturation, IDF applied inside Qdrant. Dense and sparse top-30 are fused with reciprocal-rank fusion on the client rather than the server, purely so that all three lists stay inspectable per query.

### Two pipelines, one answerer

A indexes heading-aware sections with a deterministic `Document › Section` prefix. B rewrites each section into atomic, decontextualised propositions with a light model, searches those, and hands the parent section to the answerer. Both return sections, so the answer prompt, the reranker and the evaluation are identical — only the retrieval unit differs.

### A tracer the model calls attach themselves to

A per-request tracer is bound to a context variable; the Gemini client records every embed, generate and stream call against it without any plumbing through the retrieval code. Steps carry their real start time, the API streams each one over SSE the moment it finishes, and the inspector renders a timeline that adds up.

### Thinking off, on purpose

Gemini 3.x thinks by default and the thoughts count against the output budget: a 700-token budget produced 26 answer tokens and answers cut off mid-sentence. Every generation call now runs with minimal thinking — `thinking_budget=0` is rejected by flash-lite in JSON mode; `thinking_level="minimal"` works on both models with zero thought tokens.

### Cheap by construction

Answers are cached on the normalised question with their full trace; twenty pre-drafted questions are answered once at startup and pinned, so tapping one is instant and free. Each visitor gets five live questions a day, keyed on a client id; cached answers never count. Per-IP and global daily limits sit underneath.

### Decide with a benchmark, then say what it found

Thirty hand-written questions, sixty synthetic ones with section-level ground truth, sixteen adversarial cases; five configurations run in parallel on identical index copies; answers judged for correctness, faithfulness and citation validity. The reranker changed neither the hit rate nor the MRR and cost 1.1 s per question, so it is off by default — and still one click away, fully traced.

## Measured results

- **98.9%** — hit@final, every config (The ground-truth section was among the five passages handed to the answerer; recall at the candidate stage ≥ 98.9%. Retrieval is not the bottleneck on a 269-section corpus.)
- **≈1.0** — faithfulness (judged) (Every configuration; the 'passages are data, cite or decline' rule holds.)
- **2.3 s** — median end-to-end, winning config (Pipeline A, no rerank, no expansion. 3.6 s with the reranker on, 4.7 s with expansion — for the same hit rate.)
- **15 / 16** — adversarial cases passed (Injection, PII fishing, false premises, off-topic, Hinglish, oversized input. The miss: an emoji-only input answered cheerfully instead of asking for clarification.)

## What the numbers do and do not claim

The judge is a model, the benchmark is small, and the finding that the reranker does not help is specific to this corpus — short, self-contained sections about one person, measured on the 36-document corpus before this project was added to it. The interesting part is not the accuracy number; it is that every stage is visible, so you can see for yourself where an answer came from.

## Lessons

- If a stage costs latency, measure whether it earns it — then say so, even when it is the showcase feature.
- Make the pipeline visible and the accuracy claim becomes checkable.
- Read the model's usage metadata before blaming the prompt: 670 thought tokens explained the truncation.

