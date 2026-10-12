# portfolio-rag — "Ask about Aditya"

A retrieval-augmented chatbot for [adityamukhopadhyay.vercel.app](https://adityamukhopadhyay.vercel.app). It answers questions about
Aditya's work from his own project documents, cites the source, and links to the page it came from.

Nothing runs locally in production: the API and the vector database both run on Railway; embeddings and generation are Gemini.

```
 site (Next.js, Vercel) ──POST /chat (SSE)──▶  rag-api (FastAPI, Railway)  ──▶  Qdrant (Railway, private network)
                                                     │                              dense (Gemini 768-d) + sparse (BM25, IDF server-side)
                                                     └──▶ Gemini: embeddings · rerank/expand (flash-lite) · answer (flash)
```

## The two pipelines under test

| | A — sections | B — propositions → parent |
|---|---|---|
| unit indexed | one markdown section (heading-aware, long ones split at ~380 words) with a deterministic `Document › Section` prefix | atomic, decontextualised statements extracted from each section by `gemini-2.5-flash-lite` at ingest |
| retrieval | hybrid dense + BM25, RRF | hybrid over propositions, grouped by parent section (score = its top-3 propositions), parent text fetched |
| shared | optional query expansion (×3 queries, RRF-merged) · listwise rerank (flash-lite) · identical answer prompt with `[n]` citations |

`eval/run_eval.py` scores **A, A+qx, B, B+qx, A-norerank** on 30 curated + N synthetic + 16 adversarial questions and writes
`eval/EVAL_REPORT.md`. `--persist` writes the winner into `.env` (`ACTIVE_PIPELINE`, `QUERY_EXPANSION`); set the same on Railway.

## Layout

```
corpus/          generated markdown (docs/ from the .docx set, profile/, site/) — the ONLY thing the index is built from
scripts/         convert_corpus.py (docx + resume + site content → corpus), redact.py (+ redact_terms.txt)
rag/             corpus loader · chunking (A/B) · sparse BM25 · gemini client · qdrant store · pipelines · rerank · answer · guards · cache · ingest
api/             FastAPI: /chat (SSE), /chat/sync, /health, /docs, /admin/ingest, /admin/stats · in-process rate limiter
eval/            curated.json · adversarial.json · golden.py (synthetic set) · run_eval.py (A/B) · load_test.py · stress.py
tests/           unit tests, no network
```

## Run locally

```bash
python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env            # put GEMINI_API_KEY in it; leave QDRANT_URL empty → embedded Qdrant at .qdrant/
.venv/bin/python scripts/convert_corpus.py      # rebuild corpus/ from the sources
.venv/bin/python -m rag.ingest                  # embed + upsert both collections
.venv/bin/uvicorn api.main:app --reload         # http://localhost:8000
```

## Evaluate

```bash
.venv/bin/python -m eval.golden --n 120         # synthetic questions with section-level ground truth
.venv/bin/python -m eval.run_eval --persist     # A/B → eval/EVAL_REPORT.md, winner → .env
.venv/bin/python -m eval.stress    --url https://<api>
.venv/bin/python -m eval.load_test --url https://<api> --concurrency 25 --total 200
```

## Deploy on Railway (one project, two services)

1. **qdrant** — new service from the Docker image `qdrant/qdrant:latest`; add a volume mounted at `/qdrant/storage`;
   variable `QDRANT__SERVICE__API_KEY=<random>`. No public domain needed — the API reaches it over private networking.
2. **rag-api** — service from this repo (Dockerfile). Variables:
   `GEMINI_API_KEY`, `QDRANT_URL=http://qdrant.railway.internal:6333`, `QDRANT_API_KEY=<same as above>`,
   `ADMIN_TOKEN=<random>`, `ACTIVE_PIPELINE`, `QUERY_EXPANSION`, `PUBLIC_DOCS=false`, `CORS_ORIGINS=https://adityamukhopadhyay.vercel.app`.
   Generate a public domain. Health check: `/health` (503 until the index exists).
3. **Index on the server**: `curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" https://<api>/admin/ingest`
   — the embedding pipeline runs inside the API service, so nothing is built on a laptop.
   The index records the embedding model and a hash of the corpus that built it (`index_meta` collection). On start,
   if `EMBED_MODEL` changed the API re-ingests in the background and serves sparse-only (BM25) until done; if only the
   corpus changed (a document added or edited and the image rebuilt), it re-ingests in place with dense search on.
   So adding a document = write `corpus/docs/<nn>-<slug>.md`, push, redeploy; no manual `/admin/ingest` needed.

### Embedding outages

`gemini-embedding-001` started returning intermittent `429 RESOURCE_EXHAUSTED` (shared model capacity, not key quota)
in October 2026, which surfaced as `retrieval failed: ClientError` after ~17 s of retries. Since then: the default model
is `gemini-embedding-2`, query embedding retries 3× (~3.5 s) and then falls back to sparse-only retrieval, and the
error event carries the HTTP status. A dense outage is visible in the inspector as `embed_query.fallback` and
`rrf_fusion.dense_unavailable`.
4. **Site**: set `NEXT_PUBLIC_RAG_API_URL=https://<api>` on Vercel (or rely on the default in `AskWidget.tsx`).

## Guardrails

Input cleaning + length cap · per-IP and daily rate limits · prompt-injection hardening (passages are framed as data) ·
output scrub for non-public contact details · corpus redaction at build time (`scripts/redact.py`) · `PUBLIC_DOCS` gate on raw
document serving · answer cache keyed on the normalised question.

## Corpus provenance

`corpus/` is generated from my project write-ups (.docx), my resume source, my engineering story bank and the portfolio
site's profile and project pages, plus the hand-written `corpus/profile/facts.md`. Re-run `scripts/convert_corpus.py`
after any of those change, then re-ingest.

This public copy ships only the corpus files that are already public (profile, site pages) and the write-ups for my own
projects. The write-ups and screenshots for the systems I built at work stay private — the deployed assistant indexes
them, so it can answer questions about that work, but the raw documents aren't published. Names and internal words in
the private corpus are removed by `scripts/redact.py` (add terms to `scripts/redact_terms.txt`, see the `.example`).
