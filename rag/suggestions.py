"""
Pre-drafted questions shown as tap-to-ask chips. Their answers (with the full pipeline trace) are
computed once at startup and pinned in the cache with no expiry, so tapping one is instant and the
UI still shows exactly how the answer was produced.
"""
from __future__ import annotations
import threading, time
from . import answer as ans, guards, cache, trace as tr
from .config import settings

SUGGESTIONS: list[dict] = [
    {"group": "Do you know…", "q": "Do you know the Model Context Protocol (MCP)?"},
    {"group": "Do you know…", "q": "Do you know how to build RAG and semantic search systems?"},
    {"group": "Do you know…", "q": "Do you know LangChain or LangGraph?"},
    {"group": "Do you know…", "q": "Do you know FastAPI, PostgreSQL and AWS?"},
    {"group": "Have you worked on…", "q": "Have you worked on multi-agent systems in production?"},
    {"group": "Have you worked on…", "q": "Have you worked on WhatsApp or conversational AI?"},
    {"group": "Have you worked on…", "q": "Have you worked on computer vision?"},
    {"group": "Have you worked on…", "q": "Have you worked with money-moving systems or payments?"},
    {"group": "How did you build…", "q": "How does your WhatsApp sales agent avoid lying about orders?"},
    {"group": "How did you build…", "q": "How does your delivery fleet handle ~20 concurrent rider agents?"},
    {"group": "How did you build…", "q": "How is your Buyer MCP authenticated and scoped per buyer?"},
    {"group": "How did you build…", "q": "How did you build this chatbot, and what did the A/B evaluation find?"},
    {"group": "What went wrong…", "q": "What was the updated_at incident and what rule came out of it?"},
    {"group": "What went wrong…", "q": "What production failures have you handled, and what changed after?"},
    {"group": "About you", "q": "What's your background, education and current role?"},
    {"group": "About you", "q": "Have you led a team, and how do you work with stakeholders?"},
    {"group": "About you", "q": "Which LLM providers and models have you used?"},
    {"group": "About you", "q": "Are you actually Aditya? How can I reach the real you?"},
    {"group": "About you", "q": "Did you lead the search, matching and clustering ML work?"},
    {"group": "About you", "q": "Which of your projects handle real money?"},
]

_state = {"warmed": 0, "total": len(SUGGESTIONS), "running": False, "started_at": None, "errors": 0}

def status() -> dict:
    return dict(_state)

def warm(api_base: str = "", pipeline: str | None = None, log=print):
    """Answer every suggestion once and pin it in the cache (no expiry)."""
    if _state["running"]:
        return
    _state.update(running=True, started_at=time.time(), warmed=0, errors=0)
    p = (pipeline or settings.active_pipeline).lower()
    for s in SUGGESTIONS:
        q = guards.clean_query(s["q"])
        key = cache.TTLCache.key(q, p)
        if cache.answers.get(key):
            _state["warmed"] += 1; continue
        try:
            tracer = tr.Tracer()
            trace, sources, prompt = ans.prepare(q, pipeline=p, api_base=api_base, tracer=tracer)
            text = guards.scrub_output(ans.answer_sync(prompt, tracer))
            td = tracer.to_dict() | {"pipeline": p, "queries": trace.queries, "question": q, "precomputed": True}
            cache.answers.put(key, {"answer": text, "sources": ans.sources_json(sources), "trace": td}, pin=True)
            _state["warmed"] += 1
            log(f"warmed {_state['warmed']}/{_state['total']}: {q[:50]}")
        except Exception as e:  # noqa: BLE001
            _state["errors"] += 1; log(f"warm failed: {q[:40]} {type(e).__name__}")
    _state["running"] = False

def warm_in_background(api_base: str = ""):
    threading.Thread(target=warm, args=(api_base,), daemon=True).start()
