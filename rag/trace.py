"""
Per-query pipeline tracing. Every stage records its duration and its inputs/outputs so the UI can show
exactly what the pipeline did: the expanded queries, the dense and sparse top-K, the fused candidate
list, what the reranker received and how it reordered it, the final passages, every model call, and
the generation timing. A tracer is bound to the current context (contextvar) so the Gemini client can
attach model calls without plumbing.
"""
from __future__ import annotations
import contextvars, time
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from typing import Any, Callable

@dataclass
class Step:
    name: str
    ms: float
    data: dict[str, Any] = field(default_factory=dict)
    t_start: float = 0.0     # seconds since the tracer started

@dataclass
class Call:
    kind: str        # embed | generate | stream
    model: str
    ms: float
    detail: dict[str, Any] = field(default_factory=dict)

class Tracer:
    def __init__(self, on_step: Callable[[Step], None] | None = None):
        self.t0 = time.perf_counter()
        self.steps: list[Step] = []
        self.calls: list[Call] = []
        self.on_step = on_step

    @contextmanager
    def step(self, name: str, **data):
        t = time.perf_counter()
        holder: dict[str, Any] = dict(data)
        try:
            yield holder
        finally:
            s = Step(name=name, ms=(time.perf_counter() - t) * 1000, data=holder, t_start=t - self.t0)
            self.steps.append(s)
            if self.on_step:
                try: self.on_step(s)
                except Exception: pass  # noqa: BLE001 — never let UI plumbing break retrieval

    def add(self, name: str, ms: float, started: float | None = None, **data):
        """Record a step measured elsewhere. `started` is the perf_counter() at which it began."""
        t_start = (started - self.t0) if started is not None else (time.perf_counter() - self.t0 - ms / 1000)
        s = Step(name=name, ms=ms, data=data, t_start=max(0.0, t_start))
        self.steps.append(s)
        if self.on_step:
            try: self.on_step(s)
            except Exception: pass  # noqa: BLE001

    def call(self, kind: str, model: str, ms: float, **detail):
        self.calls.append(Call(kind=kind, model=model, ms=ms, detail=detail))

    def to_dict(self) -> dict:
        return {"total_ms": round((time.perf_counter() - self.t0) * 1000),
                "steps": [{"name": s.name, "ms": round(s.ms, 1), "at_ms": round(s.t_start * 1000), "data": s.data} for s in self.steps],
                "calls": [asdict(c) | {"ms": round(c.ms, 1)} for c in self.calls]}

_current: contextvars.ContextVar[Tracer | None] = contextvars.ContextVar("tracer", default=None)

def current() -> Tracer | None:
    return _current.get()

def bind(t: Tracer | None):
    return _current.set(t)

def unbind(token):
    _current.reset(token)

def hit_view(payload: dict, score: float, rank: int, **extra) -> dict:
    """Compact, UI-safe view of a retrieved unit."""
    text = payload.get("text", "")
    return {"rank": rank, "score": round(float(score), 5), "sid": payload.get("sid"), "doc": payload.get("doc_slug"),
            "title": payload.get("doc_title"), "heading": payload.get("heading"),
            "snippet": (text[:200] + "…") if len(text) > 200 else text, "words": len(text.split()), **extra}
