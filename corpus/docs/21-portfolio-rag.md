---
title: "Ask-about-Aditya — Glass-Box RAG Chatbot for the Portfolio"
slug: "portfolio-rag"
kind: "project"
site_slug: "portfolio-rag"
page_url: "https://adityamukhopadhyay.vercel.app/work/portfolio-rag"
source: "hand-written project document, 2026-09-17"
summary: "A retrieval-augmented chatbot over Aditya's own project documents, served on his portfolio site, that exposes its entire pipeline per question — dense and sparse top-K, RRF fusion, listwise reranking with reasons, and every model call with its latency — with two chunking strategies A/B-evaluated on a judged benchmark."
---
# Ask-about-Aditya — Glass-Box RAG Chatbot for the Portfolio

## 1. Summary

Ask-about-Aditya is a personal project by Aditya Mukhopadhyay: a retrieval-augmented generation (RAG) chatbot embedded in his portfolio website (adityamukhopadhyay.vercel.app/ask) that answers questions about his work, skills and projects from his own project documents, and cites the document each claim came from. Its distinguishing feature is that it is a glass box: for every question, the interface streams the full retrieval pipeline as it runs — the expanded queries, the dense and sparse top-K candidates with scores, the reciprocal-rank fusion, the reranker's before-and-after ordering with a one-line reason per passage, the prompt that was built, and every model call with its latency and token counts.

Aditya built it in a single day in September 2026, from corpus conversion through deployment. It is hosted on Railway (FastAPI backend and a Qdrant vector database on a private network) with Gemini models for embeddings, reranking and generation, and the front end is part of his Next.js portfolio on Vercel. Two retrieval pipelines were built and A/B-evaluated on a judged benchmark; the winner is persisted as the production configuration.

## 2. Tech Stack & Infrastructure

- Backend: Python 3.11, FastAPI, Server-Sent Events (sse-starlette) for streaming, pydantic-settings for configuration.
- Vector database: Qdrant (open source), one instance on Railway with a persistent volume, reached over Railway's private network; embedded local mode for development and evaluation.
- Embeddings: Gemini `gemini-embedding-2` (moved from `gemini-embedding-001` in October 2026 after Google began capacity-throttling it with intermittent 429 errors), 768 dimensions (Matryoshka truncation), unit-normalised, dot-product similarity; task types RETRIEVAL_DOCUMENT and RETRIEVAL_QUERY. If the embedding call still fails after three retries, retrieval degrades to sparse-only (BM25) instead of returning an error, and the inspector marks the fusion step "dense unavailable". The index records which model built it; on startup the API re-indexes itself in the background if the configured model differs, running sparse-only until the rebuild completes.
- Sparse retrieval: a BM25-style encoder written from scratch (hashed term ids, term-frequency saturation), with IDF applied inside Qdrant's sparse-vector index — no model download, no external service.
- Models: `gemini-3.5-flash` for answers and as the evaluation judge; `gemini-3.5-flash-lite` for query expansion, listwise reranking and proposition extraction.
- Front end: Next.js 16 (static export) on Vercel, React 19, Tailwind CSS v4; a floating widget on every page and a full `/ask` page with a pipeline inspector panel.
- Infrastructure: Railway project provisioned through its GraphQL API (services, volume, variables, domain) because the CLI rejected a workspace-scoped token; Vercel for the site; GitHub (private repository `adityamukhopadhyay/portfolio-rag`).
- Corpus tooling: python-docx for the 20 project documents, Node's native TypeScript stripping to read the site's content files, a pattern-based redaction layer, and a hand-written facts file.

## 3. System Architecture

### 3.1 Corpus pipeline (build time)

A converter turns every source about Aditya into a canonical markdown corpus with frontmatter (title, slug, kind, page URL): the 20 project documents (.docx) with headings, lists, tables and embedded screenshots preserved; the resume source of truth; the engineering story bank; the portfolio site's own profile and project pages; and a hand-written facts file. Every string passes through a redaction layer (emails, phone numbers, secrets, internal hostnames, IPs, a denylist) before it is written, because the corpus is served to the public internet. At the time of the evaluation the corpus was 36 markdown files, about 20,000 words, 267 sections; this project's own document and portfolio page were added afterwards, so the served index is 38 documents and 290 sections (the counts shown in the chat header are read live from the API). Each document carries its portfolio page URL so that citations link to the human-readable page rather than the raw file.

The facts file deliberately holds negative knowledge — what Aditya does not use (LangChain, LlamaIndex, CrewAI) and what is not on record — so that questions like "does he use LangChain" are answered from a stated fact rather than from the absence of evidence.

### 3.2 Indexing — the two pipelines under test

Both pipelines split documents into heading-aware sections (tiny sections merged into their neighbour, long ones split at about 380 words on paragraph boundaries) and embed each unit with both a dense vector and a sparse BM25 vector.

- Pipeline A (sections): the unit is the section itself, embedded with a deterministic situating prefix — "Document: … / Section: …" — so the embedding carries its context. 269 units at evaluation time (290 now).
- Pipeline B (propositions → parent): `gemini-3.5-flash-lite` rewrites each section into atomic, decontextualised statements (the subject is always named, never "he" or "it"). The propositions are what is searched; the parent section is what the answerer reads (small-to-big retrieval). 2,009 propositions pointing at 269 parents at evaluation time; the served index is larger now that this project's own documents are included (live counts are shown in the chat header).

### 3.3 Query pipeline (per request)

1. Guard: NFKC normalisation, control-character stripping, a 1,000-character cap, injection and PII pattern flags.
2. Rate limiting (per IP per minute, a global daily budget, and a per-visitor daily quota on uncached questions) and an answer cache keyed on the normalised question.
3. Optional follow-up rewrite: if the question refers to earlier turns ("that one", "it"), the light model rewrites it to stand alone.
4. Optional query expansion: two alternative phrasings from the light model; each is searched and the results fused.
5. Embed the query; dense top-30 and sparse top-30 from Qdrant; reciprocal-rank fusion computed client-side (k = 60) so every intermediate list stays inspectable; across expanded queries, RRF again.
6. Pipeline B only: group proposition hits by parent section (a section scores the sum of its top-3 propositions) and fetch the parent text.
7. Optional listwise rerank: one call to the light model with the 20 candidates returns an order and a one-line reason per passage.
8. Build the prompt: the final five passages are numbered [1]–[5] and framed as data; the system prompt requires citations, first-person voice, and a plain "I haven't written that down" when the passages do not cover the question.
9. Stream the answer from `gemini-3.5-flash`; scrub the output for non-public contact details; cache it with its trace.

Every stage records its duration and its inputs and outputs on a tracer bound to the request. The API streams each step to the browser the moment it finishes (SSE `step` events), then the sources, then the answer tokens, then the complete trace.

### 3.4 Front end

The assistant answers in the first person as an AI version of Aditya — a visitor's "you" means Aditya — and a deterministic, traced rewrite turns second person into third for the search query only ("Do you know MCP?" → "does Aditya know MCP?"). The chat is deliberately minimal: a header with Aditya's portrait and a live status line ("AI version of me · answers from my N project documents", counts read from the API), four suggested questions with a "more" link, plain-text answers with superscript citations that show the source on hover, and an icon row per answer (sources, inspect, copy) with tooltips. The inspector is a separate panel: a timeline of the steps that took real time, then one row per step with a line icon and its duration, each collapsed until opened — the fusion row shows the fused candidates with their dense and sparse ranks, the rerank row shows each passage's move (for example "15 → 2 ▲13") with the model's stated reason, and model calls fold away at the bottom. Retrieval settings (pipeline A or B, expansion, rerank) live behind a single settings glyph as segmented controls.

Twenty pre-drafted questions ("Does Aditya know …", "Has Aditya worked on …", "How did he build …", "What went wrong …") are answered once at startup and pinned in the cache with their full trace, so tapping one is instant and still shows how the answer was produced; they do not count against a visitor's quota.

## 4. Key Engineering Features

- Glass-box tracing: a `Tracer` with a context-variable binding lets the Gemini client attach model calls to the current request without any plumbing through the retrieval code; steps carry their real start time so the timeline is exact.
- Client-side RRF instead of Qdrant's server-side fusion, purely so that the dense list, the sparse list and the fused list are all visible per query.
- Gemini 3.x "thinking" is switched to minimal on every generation call. With defaults, thinking tokens count against `max_output_tokens`: a 700-token budget produced 26 answer tokens and answers cut off mid-sentence. `thinking_budget=0` is rejected by flash-lite in JSON mode; `thinking_level="minimal"` works on both models with zero thought tokens.
- Answer cache with pinned entries (pre-drafted questions never expire) and an LRU bound; cached replays return in single-digit milliseconds with the original trace.
- Per-visitor quota: five live (uncached) questions per 24 hours in production, keyed on a client-generated id with an IP fallback; unlimited locally. Cached answers are free, so the suggested questions always work.
- Prompt-injection hardening: passages are labelled as data and the system prompt instructs the model to ignore embedded instructions; an adversarial test set (injection, PII fishing, false premises, off-topic, Hinglish, oversized input) exercises it.
- Provisioning through Railway's GraphQL API: services, the Qdrant volume, variables and the public domain are created idempotently from a script, with secrets forwarded straight from the local environment file and never printed.
- Ingestion runs on the server (`POST /admin/ingest`, bearer-protected), so the index is built where it is served.

## 5. Evaluation

A benchmark of 30 hand-written questions with reference answers, 60 synthetic questions generated per section with section-level ground truth, and 16 adversarial cases was run against five configurations — A, A with expansion, B, B with expansion, and A without reranking — each in its own process on an identical copy of the index. Retrieval was scored by whether the ground-truth section was in the candidate set and in the final five (hit@final, recall@candidates, MRR); answers were judged by `gemini-3.5-flash` for correctness against the reference, faithfulness to the passages and citation validity; adversarial cases combined regex checks with a judge.

Results (17 September 2026): every configuration placed the ground-truth section among the five passages handed to the answerer 98.9% of the time, with recall at the candidate stage at or above 98.9%, faithfulness at or near 1.0, and 15 of 16 adversarial cases passed. The reranker changed neither the hit rate nor the MRR and cost about 1.1 seconds and one extra model call per question; query expansion likewise added about 1.1 seconds for the same hit rate; propositions matched sections but did not beat them, at the cost of 269 extraction calls at ingest. The winning configuration on the composite score (0.35 correctness, 0.25 faithfulness, 0.20 hit@final, 0.10 adversarial, 0.10 latency) was pipeline A without reranking or expansion: median 2.3 seconds end to end against 3.6 seconds with the reranker on. That configuration is persisted as the production default; reranking and expansion remain one click away in the settings and are fully traced when enabled.

The honest reading is that on a 269-section corpus of short, self-contained sections, hybrid dense-plus-BM25 retrieval with RRF is already sufficient and the heavier stages do not earn their latency. The one consistent adversarial miss is an emoji-only input the model answers cheerfully instead of asking for clarification.

## 6. Failures Found and Fixed

- Two prompts contained literal JSON braces that Python's `.format()` consumed, so proposition extraction and query expansion silently failed and pipeline B indexed nothing. Fixed by escaping; caught by an end-to-end check that B returned zero results.
- sse-starlette emits CRLF line endings; the browser's SSE parser split on LF only, buffered the whole response and never emitted an event. Fixed by normalising line endings and flushing the trailing buffer.
- Externally-timed steps were recorded with their end time as their start, so the generation bar overflowed the timeline. Fixed by passing the real start time to the tracer.
- Gemini's `gemini-2.5-flash-lite` was withdrawn for new API users mid-build; the model list was read from the API and the pipeline moved to the 3.5 generation.

## 7. Business Impact & Engineering Achievements

- A working, public demonstration of end-to-end RAG engineering — corpus construction with redaction, hybrid retrieval, fusion, reranking, grounded generation with citations, caching, quotas and deployment — that a reader can interrogate rather than take on trust.
- A judged A/B benchmark with a documented, persisted decision, including the unglamorous finding that the reranker did not help on this corpus.
- Everything runs hosted: no local process is involved in serving, indexing or evaluation-time retrieval.
