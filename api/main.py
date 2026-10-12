"""
FastAPI service — glass-box mode: every pipeline stage is streamed to the client as it happens.

  POST /chat            SSE: step* → sources → token* → trace → done      (step events arrive live)
  POST /chat/sync       JSON: {answer, sources, pipeline, trace}          (eval + fallback)
  GET  /health          liveness + collection counts + usage
  GET  /docs            list of documents;  GET /docs/{slug} markdown (PUBLIC_DOCS=true)
  POST /admin/ingest    bearer-protected; runs the embedding pipeline on the server
  GET  /admin/stats     bearer-protected; cache + budget counters
"""
from __future__ import annotations
import asyncio, json, re, time
from pathlib import Path
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from rag.config import settings
from rag import answer as ans, guards, cache, store, gemini, trace as tr, suggestions, qlog
from rag.corpus import load_corpus
from .ratelimit import limiter
from .booking import router as booking_router
from .visitors import router as visitors_router

app = FastAPI(title="Aditya portfolio RAG", version="1.2")
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
                   allow_methods=["GET", "POST"], allow_headers=["*"], expose_headers=["*"])
START = time.time()
app.include_router(booking_router)
app.include_router(visitors_router)

class ChatIn(BaseModel):
    question: str = Field(..., max_length=4000)
    pipeline: str | None = None          # "a" | "b" — A/B override; default = settings.active_pipeline
    history: list[dict] | None = None    # [{role, content}] last few turns, used only to rewrite follow-ups
    expand: bool | None = None           # override query expansion for this request
    rerank: bool | None = None           # override reranking for this request
    nocache: bool = False

def _api_base(req: Request) -> str:
    return str(req.base_url).rstrip("/")

def _user_id(req: Request) -> str:
    """Per-visitor key: a client-generated id header, else the IP."""
    cid = (req.headers.get("x-client-id") or "").strip()[:64]
    return f"c:{cid}" if cid else f"ip:{_client_ip(req)}"

def _is_admin(req: Request) -> bool:
    return bool(settings.admin_token) and req.headers.get("authorization") == f"Bearer {settings.admin_token}"

def _remaining(req: Request):
    return None if _is_admin(req) else limiter.remaining(_user_id(req), _client_ip(req))

def _consume(req: Request):
    if not _is_admin(req): limiter.consume(_user_id(req), _client_ip(req))

def _err(e: Exception) -> str:
    """'ClientError 429 RESOURCE_EXHAUSTED' rather than a bare class name, so the inspector says what actually failed."""
    code = getattr(e, "code", None) or getattr(e, "status_code", None)
    status = getattr(e, "status", None)
    return " ".join(str(x) for x in (type(e).__name__, code, status) if x)

QUOTA_MSG = "You've used today's {n} live questions. The pre-drafted questions still work — they're answered from cache — and the limit resets in 24 hours."

def _client_ip(req: Request) -> str:
    return (req.headers.get("x-forwarded-for") or (req.client.host if req.client else "?")).split(",")[0].strip()

def _pipeline(p: str | None) -> str:
    p = (p or settings.active_pipeline).lower()
    return p if p in ("a", "b") else settings.active_pipeline

_FOLLOWUP = """Rewrite the final user question so it stands alone, using the conversation for context. Keep it short. Output only the rewritten question.

{history}
Final question: {q}"""

def _resolve_followup(q: str, history: list[dict] | None, t: tr.Tracer) -> str:
    if not history:
        return q
    turns = [h for h in history[-6:] if isinstance(h, dict) and h.get("role") in ("user", "assistant") and h.get("content")]
    if not turns or not re.search(r"(?i)\b(it|that|this|they|those|he|his|the (project|system|one))\b", q):
        return q
    hist = "\n".join(f"{t_['role']}: {str(t_['content'])[:400]}" for t_ in turns)
    with t.step("followup_rewrite", model=settings.light_model, turns=len(turns)) as h:
        try:
            out = gemini.generate(_FOLLOWUP.format(history=hist, q=q), model=settings.light_model, temperature=0.0, max_tokens=80).strip() or q
        except Exception as e:  # noqa: BLE001
            out = q; h["error"] = type(e).__name__
        h["from"] = q; h["to"] = out
        return out

def _followup_bound(q: str, history, t: tr.Tracer) -> str:
    tok = tr.bind(t)
    try:
        return _resolve_followup(q, history, t)
    finally:
        tr.unbind(tok)

def _guard(req: Request, body: ChatIn, t: tr.Tracer) -> tuple[str, str]:
    if not _is_admin(req):                      # admin bearer = load/stress tests; everything else is limited
        ok, why = limiter.check(_client_ip(req))
        if not ok:
            raise HTTPException(429, why)
    with t.step("guard", max_chars=settings.max_query_chars) as h:
        try:
            q = guards.clean_query(body.question)
        except guards.Rejected as e:
            raise HTTPException(e.status, e.reason)
        h.update(guards.classify(q)); h["chars"] = len(q)
    return q, _pipeline(body.pipeline)

def _opts(body: ChatIn) -> dict:
    return {"use_expansion": body.expand, "do_rerank": body.rerank}

@app.post("/chat")
async def chat(req: Request, body: ChatIn):
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    tracer = tr.Tracer(on_step=lambda s: loop.call_soon_threadsafe(queue.put_nowait, s))
    token = tr.bind(tracer)
    try:
        q, pipeline = _guard(req, body, tracer)
    finally:
        tr.unbind(token)
    uid = _user_id(req)
    raw_cached = (not body.nocache) and cache.answers.get(cache.TTLCache.key(q, pipeline)) is not None
    if not raw_cached and _remaining(req) == 0:
        raise HTTPException(429, QUOTA_MSG.format(n=settings.rate_limit_per_user))

    def step_evt(s: tr.Step):
        return {"event": "step", "data": json.dumps({"name": s.name, "ms": round(s.ms, 1), "at_ms": round(s.t_start * 1000), "data": s.data}, default=str)}

    async def gen():
        # steps recorded so far (guard)
        for s in tracer.steps:
            yield step_evt(s)
        while not queue.empty(): queue.get_nowait()
        q2 = await asyncio.to_thread(_followup_bound, q, body.history, tracer)
        while not queue.empty(): yield step_evt(queue.get_nowait())
        cached = None if body.nocache else cache.answers.get(cache.TTLCache.key(q2, pipeline))
        if cached and body.expand is None and body.rerank is None:
            tracer.add("cache", 0.2, started=time.perf_counter(), hit=True, precomputed=bool(cached["trace"].get("precomputed")))
            while not queue.empty(): yield step_evt(queue.get_nowait())
            yield {"event": "sources", "data": json.dumps(cached["sources"])}
            yield {"event": "token", "data": json.dumps(cached["answer"])}
            yield {"event": "trace", "data": json.dumps(cached["trace"], default=str)}
            qlog.record(q2, pipeline=pipeline, cached=True, precomputed=bool(cached["trace"].get("precomputed")), uid=uid,
                        latency_ms=None, answer=cached["answer"], sources=[s["doc_slug"] for s in cached["sources"]])
            yield {"event": "done", "data": json.dumps({"cached": True, "pipeline": pipeline, "remaining": _remaining(req)})}
            return
        if _remaining(req) == 0:
            yield {"event": "error", "data": json.dumps({"message": QUOTA_MSG.format(n=settings.rate_limit_per_user), "quota": True, "remaining": 0})}
            return
        _consume(req)
        tracer.add("cache", 0.1, started=time.perf_counter(), hit=False)
        while not queue.empty(): yield step_evt(queue.get_nowait())

        fut = asyncio.create_task(asyncio.to_thread(ans.prepare, q2, pipeline, _api_base(req), tracer, **_opts(body)))
        while not fut.done():
            try:
                s = await asyncio.wait_for(queue.get(), timeout=0.15); yield step_evt(s)
            except asyncio.TimeoutError:
                pass
        while not queue.empty(): yield step_evt(queue.get_nowait())
        try:
            trace, sources, prompt = fut.result()
        except Exception as e:  # noqa: BLE001
            yield {"event": "error", "data": json.dumps({"message": f"retrieval failed: {_err(e)}"})}
            return
        yield {"event": "sources", "data": json.dumps(ans.sources_json(sources))}
        buf = []
        try:
            async for tok in ans.stream_answer(prompt, tracer):
                buf.append(tok)
                yield {"event": "token", "data": json.dumps(tok)}
        except Exception as e:  # noqa: BLE001
            yield {"event": "error", "data": json.dumps({"message": f"generation failed: {_err(e)}"})}
            return
        while not queue.empty(): yield step_evt(queue.get_nowait())
        full = guards.scrub_output("".join(buf))
        td = tracer.to_dict() | {"pipeline": pipeline, "queries": trace.queries, "question": q2}
        cache.answers.put(cache.TTLCache.key(q2, pipeline), {"answer": full, "sources": ans.sources_json(sources), "trace": td})
        qlog.record(q2, pipeline=pipeline, cached=False, precomputed=False, uid=uid, latency_ms=td["total_ms"], answer=full,
                    sources=[s.doc_slug for s in sources])
        yield {"event": "trace", "data": json.dumps(td, default=str)}
        yield {"event": "done", "data": json.dumps({"cached": False, "pipeline": pipeline, "total_ms": td["total_ms"], "remaining": _remaining(req)})}
    return EventSourceResponse(gen(), ping=15)

@app.post("/chat/sync")
async def chat_sync(req: Request, body: ChatIn):
    tracer = tr.Tracer()
    token = tr.bind(tracer)
    try:
        q, pipeline = _guard(req, body, tracer)
        q = await asyncio.to_thread(_resolve_followup, q, body.history, tracer)
    finally:
        tr.unbind(token)
    if _remaining(req) == 0:
        raise HTTPException(429, QUOTA_MSG.format(n=settings.rate_limit_per_user))
    _consume(req)
    trace, sources, prompt = await asyncio.to_thread(ans.prepare, q, pipeline, _api_base(req), tracer, **_opts(body))
    text = guards.scrub_output(await asyncio.to_thread(ans.answer_sync, prompt, tracer))
    td = tracer.to_dict() | {"pipeline": pipeline, "queries": trace.queries, "question": q,
                             "candidates": [c.sid for c in trace.candidates], "final": [c.sid for c in trace.final],
                             "t_retrieve_ms": round(trace.t_retrieve_ms), "t_rerank_ms": round(trace.t_rerank_ms)}
    qlog.record(q, pipeline=pipeline, cached=False, precomputed=False, uid=_user_id(req), latency_ms=td["total_ms"], answer=text,
                sources=[s.doc_slug for s in sources])
    return {"answer": text, "sources": ans.sources_json(sources), "pipeline": pipeline, "trace": td}

@app.get("/health")
async def health():
    try:
        counts = {settings.collection_sections: store.count(settings.collection_sections),
                  settings.collection_props: store.count(settings.collection_props)}
        ok = counts[settings.collection_sections] > 0
    except Exception as e:  # noqa: BLE001
        counts, ok = {"error": type(e).__name__}, False
    return JSONResponse(status_code=200 if ok else 503, content={
        "ok": ok, "pipeline": settings.active_pipeline, "query_expansion": settings.query_expansion, "rerank": settings.rerank,
        "models": {"embed": settings.embed_model, "answer": settings.answer_model, "light": settings.light_model},
        "collections": counts, "documents": len(_docs()), "uptime_s": int(time.time() - START), "gemini_calls": gemini.Usage.calls,
        "cache": {"hits": cache.answers.hits, "misses": cache.answers.misses}, "public_docs": settings.public_docs})

# ---------------------------------------------------------------- documents
_DOCS: dict[str, tuple[str, Path, str | None]] | None = None
def _docs():
    global _DOCS
    if _DOCS is None:
        _DOCS = {d.slug: (d.title, d.path, d.page_url) for d in load_corpus()}
    return _DOCS

@app.get("/docs")
async def list_docs():
    return [{"slug": s, "title": t, "page_url": u, "doc_url": f"/docs/{s}" if settings.public_docs else None}
            for s, (t, _, u) in sorted(_docs().items())]

@app.get("/docs/{slug}", response_class=PlainTextResponse)
async def get_doc(slug: str):
    if not settings.public_docs:
        raise HTTPException(404, "documents are not published")
    d = _docs().get(slug)
    if not d:
        raise HTTPException(404, "no such document")
    text = d[1].read_text(encoding="utf-8")
    return re.sub(r"^---\n.*?\n---\n", "", text, count=1, flags=re.S)

# ---------------------------------------------------------------- admin
def _admin(authorization: str = Header(default="")):
    if not settings.admin_token or authorization != f"Bearer {settings.admin_token}":
        raise HTTPException(401, "admin token required")

def _readonly(authorization: str = Header(default="")):
    """Read-only console access: the dashboard token, or the admin token."""
    ok = (settings.dashboard_token and authorization == f"Bearer {settings.dashboard_token}") or \
         (settings.admin_token and authorization == f"Bearer {settings.admin_token}")
    if not ok:
        raise HTTPException(401, "dashboard token required")

_ingest_job: dict = {"running": False, "log": [], "stats": None, "error": None, "started": None}

def _run_ingest(only, recreate, warm_after: bool = False):
    from rag.ingest import ingest
    _ingest_job.update(running=True, log=[], stats=None, error=None, started=time.time())
    try:
        _ingest_job["stats"] = ingest(only, recreate, _ingest_job["log"].append)
    except Exception as e:  # noqa: BLE001
        _ingest_job["error"] = f"{type(e).__name__}: {e}"[:300]
    finally:
        _ingest_job["running"] = False
        global _DOCS; _DOCS = None
    if warm_after and not _ingest_job["error"]:
        suggestions.warm_in_background("")     # pinned answers must come from the rebuilt (dense-capable) index

@app.post("/admin/ingest", dependencies=[Depends(_admin)])
async def admin_ingest(only: str | None = None, recreate: bool = False):
    """Starts the embedding pipeline as a background job (the proxy cuts long requests); poll /admin/ingest/status."""
    if _ingest_job["running"]:
        return {"started": False, "reason": "already running", **_ingest_status()}
    import threading
    threading.Thread(target=_run_ingest, args=(only, recreate), daemon=True).start()
    return {"started": True, "only": only, "recreate": recreate}

def _ingest_status():
    return {"running": _ingest_job["running"], "elapsed_s": round(time.time() - _ingest_job["started"]) if _ingest_job["started"] else None,
            "log": _ingest_job["log"][-5:], "stats": _ingest_job["stats"], "error": _ingest_job["error"]}

@app.get("/admin/ingest/status", dependencies=[Depends(_admin)])
async def admin_ingest_status():
    return _ingest_status()

@app.get("/admin/questions", dependencies=[Depends(_readonly)])
async def admin_questions(days: int = 7, limit: int = 500):
    """Questions asked in the last `days` days (rolling 7-day retention on disk), newest first, plus a summary."""
    rows = qlog.read(min(days, qlog.RETENTION_DAYS))
    return {"summary": qlog.summary(min(days, qlog.RETENTION_DAYS)), "questions": list(reversed(rows))[:limit]}

@app.get("/admin/bookings", dependencies=[Depends(_readonly)])
async def admin_bookings():
    from .booking import LOG
    try:
        rows = [json.loads(l) for l in open(LOG, encoding="utf-8") if l.strip()]
    except FileNotFoundError:
        rows = []
    return {"count": len(rows), "bookings": rows[-100:]}

@app.get("/admin/stats", dependencies=[Depends(_readonly)])
async def admin_stats():
    return {"cache": {"hits": cache.answers.hits, "misses": cache.answers.misses, "size": len(cache.answers._d)},
            "limiter": limiter.snapshot(), "gemini": {"calls": gemini.Usage.calls, "prompt_tokens": gemini.Usage.prompt,
                                                       "output_tokens": gemini.Usage.output}}

@app.get("/quota")
async def quota(req: Request):
    return {"limit": settings.rate_limit_per_user or None, "remaining": _remaining(req), "window_h": 24}

@app.get("/suggestions")
async def get_suggestions():
    p = settings.active_pipeline
    return {"pipeline": p, "warm": suggestions.status(),
            "items": [{"q": s["q"], "group": s["group"], "cached": cache.answers.get(cache.TTLCache.key(s["q"], p)) is not None}
                      for s in suggestions.SUGGESTIONS]}

@app.post("/admin/warm", dependencies=[Depends(_admin)])
async def admin_warm(req: Request):
    suggestions.warm_in_background(_api_base(req))
    return {"started": True, **suggestions.status()}

@app.on_event("startup")
async def _startup():
    # pre-compute the suggested questions once the index exists; harmless if it does not yet
    try:
        if store.count(settings.collection_sections) > 0 and settings.gemini_api_key:
            from rag.corpus import corpus_hash
            if store.dense_ready() and store.index_corpus_hash() == corpus_hash():
                suggestions.warm_in_background("")
            elif store.dense_ready():
                # same model, new/changed corpus docs (e.g. a project added): upsert in place with dense search on,
                # then warm the suggestions from the refreshed index
                import threading
                threading.Thread(target=_run_ingest, args=(None, False, True), daemon=True).start()
            else:
                # the index was built by a different embedding model: rebuild it in place (upserts, no downtime);
                # queries run sparse-only until it finishes, then the suggestions are warmed from the new index
                import threading
                threading.Thread(target=_run_ingest, args=(None, False, True), daemon=True).start()
    except Exception:  # noqa: BLE001
        pass

@app.get("/")
async def root():
    return {"service": "aditya-portfolio-rag", "docs": "/docs", "health": "/health"}
