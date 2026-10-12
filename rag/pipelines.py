"""
The two retrieval pipelines under test. Both return ranked parent SECTIONS (so their outputs are
directly comparable and the answerer is identical), and both share the same optional query
expansion and the same reranker. Every stage is recorded on the Tracer for the glass-box UI.

  A  hybrid over section units                          (dense + BM25, client-side RRF)
  B  hybrid over propositions → group by parent section (small-to-big), section score = sum of its
     top-3 proposition RRF scores, then fetch the parent text.
"""
from __future__ import annotations
import time
from dataclasses import dataclass, field
from . import gemini, store, trace as tr
from .config import settings
from .rerank import rerank_sections

@dataclass
class Retrieved:
    sid: str
    score: float
    doc_slug: str
    doc_title: str
    heading: str
    text: str
    page_url: str | None
    kind: str
    matched: list[str] = field(default_factory=list)   # B: the propositions that hit

@dataclass
class Trace:
    pipeline: str
    query: str
    queries: list[str]
    candidates: list[Retrieved]
    final: list[Retrieved]
    t_retrieve_ms: float
    t_rerank_ms: float
    tracer: tr.Tracer | None = None

_EXPAND_PROMPT = """Rewrite the user's question about Aditya Mukhopadhyay (AI engineer) into 2 alternative search queries that use different wording and, where relevant, the concrete technical terms an engineer would use (tool names, mechanisms, metrics). Keep the original meaning. Output JSON: {{"queries": ["...", "..."]}}

Question: {q}"""

def expand(query: str, t: tr.Tracer) -> list[str]:
    with t.step("query_expansion", model=settings.light_model) as h:
        try:
            data = gemini.generate_json(_EXPAND_PROMPT.format(q=query), model=settings.light_model, temperature=0.4, max_tokens=200)
            alts = [q for q in data.get("queries", []) if isinstance(q, str) and q.strip()][:2]
        except Exception as e:  # noqa: BLE001
            alts = []; h["error"] = type(e).__name__
        h["queries"] = [query] + alts
        return [query] + alts

import re as _re
_PERSONA = [
    (r"\b(do|did|have|has|are|were|can|could|would|will|should)\s+you\b", lambda m: {"do": "does", "have": "has", "are": "is", "were": "was"}.get(m.group(1).lower(), m.group(1).lower()) + " Aditya"),
    (r"\byourself\b", "himself"), (r"\byours\b", "Aditya's"), (r"\byour\b", "Aditya's"), (r"\byou\b", "Aditya"),
    (r"\bthis chatbot\b|\bthis assistant\b|\bthis bot\b", "the Ask-about-Aditya RAG chatbot"),
]
def persona_query(q: str) -> str:
    """The visitor addresses Aditya as 'you'; the corpus talks about 'Aditya'. Rewrite for retrieval only."""
    out = q
    for pat, rep in _PERSONA:
        out = _re.sub(pat, rep, out, flags=_re.I)
    return out

def _views(hits: list[store.Hit], n: int = 12) -> list[dict]:
    return [tr.hit_view(h.payload, h.score, i + 1, ranks=h.payload.get("_ranks")) for i, h in enumerate(hits[:n])]

def _to_retrieved(pl: dict, score: float, matched: list[str] | None = None) -> Retrieved:
    return Retrieved(sid=pl["sid"], score=score, doc_slug=pl["doc_slug"], doc_title=pl["doc_title"],
                     heading=pl["heading"], text=pl["text"], page_url=pl.get("page_url"), kind=pl.get("kind", "doc"),
                     matched=matched or [])

def _embed_queries(qs: list[str], t: tr.Tracer) -> list[list[float]] | None:
    """None ⇒ dense search is skipped and retrieval runs sparse-only (BM25). That happens when Gemini keeps
    returning 429 (model capacity, seen on gemini-embedding-001 from 2026-10) or while the index is being
    rebuilt for a new embedding model. Three tries ≈ 3.5 s worst case before falling back."""
    with t.step("embed_query", model=settings.embed_model, dim=settings.embed_dim, n=len(qs)) as h:
        if not store.dense_ready():
            h["skipped"] = f"index built with {store.index_model() or 'unknown model'}, re-indexing for {settings.embed_model}"
            h["fallback"] = "sparse-only (BM25)"
            return None
        try:
            return gemini.embed(qs, task="RETRIEVAL_QUERY", tries=3)
        except Exception as e:  # noqa: BLE001
            h["error"] = f"{type(e).__name__}: {str(e)[:160]}"
            h["fallback"] = "sparse-only (BM25)"
            return None

def _search(collection: str, qs: list[str], dense: list[list[float]] | None, k: int, t: tr.Tracer, label: str) -> list[store.Hit]:
    """Per query: dense top-K, sparse top-K, RRF; across queries: RRF again. Each stage is traced.
    dense=None (embedding unavailable) ⇒ sparse-only, and the fusion step says so."""
    fused_lists = []
    for qi, (q, d) in enumerate(zip(qs, dense if dense is not None else [None] * len(qs))):
        if d is not None:
            with t.step(f"dense_search", collection=collection, query=q, k=settings.k_dense, metric="dot(unit-norm)") as h:
                dn = store.dense_only(collection, d, settings.k_dense); h["hits"] = _views(dn)
        else:
            dn = []
        with t.step(f"sparse_search", collection=collection, query=q, k=settings.k_sparse, method="BM25 (IDF in Qdrant)") as h:
            sp = store.sparse_only(collection, q, settings.k_sparse); h["hits"] = _views(sp)
        with t.step("rrf_fusion", query=q, k=k, rrf_k=60, inputs=["dense", "sparse"] if d is not None else ["sparse"]) as h:
            if d is None:
                h["dense_unavailable"] = True
            fused = store.rrf([dn, sp])[:k]; h["hits"] = _views(fused, k)
            h["only_dense"] = sum(1 for x in fused if x.payload["_ranks"].keys() == {0})
            h["only_sparse"] = sum(1 for x in fused if x.payload["_ranks"].keys() == {1})
            h["both"] = sum(1 for x in fused if len(x.payload["_ranks"]) == 2)
        fused_lists.append(fused)
    if len(fused_lists) == 1:
        return fused_lists[0]
    with t.step("multi_query_fusion", n_queries=len(qs), k=k) as h:
        merged = store.rrf(fused_lists)[:k]; h["hits"] = _views(merged, k)
        return merged

# ------------------------------------------------------------------ A
def _retrieval_query(query: str, t: tr.Tracer) -> str:
    rq = persona_query(query)
    if rq != query:
        with t.step("persona_rewrite", rule="second person → 'Aditya' for retrieval only") as h:
            h["from"] = query; h["to"] = rq
    return rq

def retrieve_a(query: str, use_expansion: bool | None, t: tr.Tracer) -> tuple[list[Retrieved], list[str]]:
    query = _retrieval_query(query, t)
    qs = expand(query, t) if (settings.query_expansion if use_expansion is None else use_expansion) else [query]
    dense = _embed_queries(qs, t)
    hits = _search(settings.collection_sections, qs, dense, settings.k_candidates, t, "sections")
    return [_to_retrieved(h.payload, h.score) for h in hits], qs

# ------------------------------------------------------------------ B
def retrieve_b(query: str, use_expansion: bool | None, t: tr.Tracer) -> tuple[list[Retrieved], list[str]]:
    query = _retrieval_query(query, t)
    qs = expand(query, t) if (settings.query_expansion if use_expansion is None else use_expansion) else [query]
    dense = _embed_queries(qs, t)
    hits = _search(settings.collection_props, qs, dense, settings.k_candidates * 2, t, "propositions")
    with t.step("group_by_parent", rule="section score = sum of its top-3 proposition scores") as h:
        parent: dict[str, list[tuple[float, str]]] = {}
        for x in hits:
            parent.setdefault(x.payload["parent_id"], []).append((x.score, x.payload["text"]))
        ranked = sorted(((sum(s for s, _ in sorted(v, reverse=True)[:3]), sid, v) for sid, v in parent.items()), reverse=True)
        ranked = ranked[: settings.k_candidates]
        h["parents"] = [{"rank": i + 1, "sid": sid, "score": round(sc, 5), "n_props": len(v),
                         "top_props": [p for _, p in sorted(v, reverse=True)[:3]]} for i, (sc, sid, v) in enumerate(ranked)]
    with t.step("fetch_parents", n=len(ranked), collection=settings.collection_sections):
        parents = store.get_many(settings.collection_sections, [sid for _, sid, _ in ranked])
    out = []
    for sc, sid, v in ranked:
        pl = parents.get(sid)
        if pl:
            out.append(_to_retrieved(pl, sc, matched=[p for _, p in sorted(v, reverse=True)[:3]]))
    return out, qs

# ------------------------------------------------------------------ shared
def run(query: str, pipeline: str | None = None, use_expansion: bool | None = None,
        do_rerank: bool | None = None, k_final: int | None = None, tracer: tr.Tracer | None = None) -> Trace:
    pipeline = (pipeline or settings.active_pipeline).lower()
    t = tracer or tr.Tracer()
    token = tr.bind(t)
    try:
        t0 = time.perf_counter()
        cands, qs = (retrieve_b if pipeline == "b" else retrieve_a)(query, use_expansion, t)
        t1 = time.perf_counter()
        kf = k_final or settings.k_final
        if (settings.rerank if do_rerank is None else do_rerank) and len(cands) > kf:
            final = rerank_sections(query, cands, kf, t)
        else:
            with t.step("rerank", skipped=True, reason="disabled or too few candidates") as h:
                final = cands[:kf]; h["final"] = [c.sid for c in final]
        t2 = time.perf_counter()
        return Trace(pipeline=pipeline, query=query, queries=qs, candidates=cands, final=final,
                     t_retrieve_ms=(t1 - t0) * 1000, t_rerank_ms=(t2 - t1) * 1000, tracer=t)
    finally:
        tr.unbind(token)
