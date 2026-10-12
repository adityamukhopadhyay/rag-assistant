"""
Qdrant store. Two collections:
  sections      — pipeline A units; ALSO the parent store that pipeline B expands into
  propositions  — pipeline B units, each pointing at its parent section id
Both carry a dense vector (Gemini, unit-norm, dot product) and a sparse BM25 vector (IDF applied server-side).
Hybrid retrieval = Query API with two prefetches fused by RRF.
"""
from __future__ import annotations
import atexit, uuid
from dataclasses import dataclass
from typing import Any
from qdrant_client import QdrantClient, models as qm
from .config import settings
from . import sparse

DENSE, SPARSE = "dense", "bm25"

@dataclass
class Hit:
    id: str
    score: float
    payload: dict[str, Any]

_client: QdrantClient | None = None

def client() -> QdrantClient:
    global _client
    if _client is None:
        if settings.qdrant_url:
            _client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None, timeout=30)
        else:
            _client = QdrantClient(path=settings.qdrant_path)   # embedded local mode (dev / eval)
            atexit.register(lambda: _client and _client.close())
    return _client

def _pid(sid: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, sid))

def ensure_collections(recreate: bool = False):
    c = client()
    for name in (settings.collection_sections, settings.collection_props):
        exists = c.collection_exists(name)
        if exists and recreate:
            c.delete_collection(name); exists = False
        if not exists:
            c.create_collection(
                collection_name=name,
                vectors_config={DENSE: qm.VectorParams(size=settings.embed_dim, distance=qm.Distance.DOT)},
                sparse_vectors_config={SPARSE: qm.SparseVectorParams(modifier=qm.Modifier.IDF)},
            )
            for field in ("doc_slug", "kind", "parent_id"):
                try:
                    c.create_payload_index(name, field, qm.PayloadSchemaType.KEYWORD)
                except Exception:  # noqa: BLE001 — local mode may not support indexes
                    pass

def upsert(collection: str, ids: list[str], dense: list[list[float]], texts_for_sparse: list[str], payloads: list[dict]):
    if not (len(ids) == len(dense) == len(texts_for_sparse) == len(payloads)):
        raise ValueError(f"upsert {collection}: {len(ids)} ids but {len(dense)} vectors — refusing a partial index")
    pts = []
    for sid, dv, txt, pl in zip(ids, dense, texts_for_sparse, payloads):
        si, sv = sparse.encode(txt)
        pts.append(qm.PointStruct(id=_pid(sid), vector={DENSE: dv, SPARSE: qm.SparseVector(indices=si, values=sv)},
                                  payload={"sid": sid, **pl}))
    for i in range(0, len(pts), 128):
        client().upsert(collection, points=pts[i:i + 128], wait=True)

def rrf(lists: list[list["Hit"]], k: int = 60) -> list["Hit"]:
    """Reciprocal-rank fusion, computed client-side so every stage stays inspectable."""
    scores: dict[str, float] = {}; by_id: dict[str, Hit] = {}; ranks: dict[str, dict[int, int]] = {}
    for li, hits in enumerate(lists):
        for rank, h in enumerate(hits):
            scores[h.id] = scores.get(h.id, 0.0) + 1.0 / (k + rank + 1)
            by_id.setdefault(h.id, h); ranks.setdefault(h.id, {})[li] = rank + 1
    out = []
    for sid, sc in sorted(scores.items(), key=lambda x: -x[1]):
        h = by_id[sid]
        out.append(Hit(id=h.id, score=sc, payload={**h.payload, "_ranks": ranks[sid]}))
    return out

def hybrid(collection: str, query_text: str, query_dense: list[float], k: int,
           k_dense: int | None = None, k_sparse: int | None = None) -> tuple[list["Hit"], list["Hit"], list["Hit"]]:
    """Returns (fused top-k, dense list, sparse list)."""
    dense = dense_only(collection, query_dense, k_dense or settings.k_dense)
    sp = sparse_only(collection, query_text, k_sparse or settings.k_sparse)
    fused = rrf([dense, sp])[:k]
    return fused, dense, sp

def dense_only(collection: str, query_dense: list[float], k: int) -> list[Hit]:
    res = client().query_points(collection, query=query_dense, using=DENSE, limit=k, with_payload=True)
    return [Hit(id=p.payload["sid"], score=float(p.score), payload=p.payload) for p in res.points]

def sparse_only(collection: str, query_text: str, k: int) -> list[Hit]:
    qi, qv = sparse.encode_query(query_text)
    if not qi:
        return []
    res = client().query_points(collection, query=qm.SparseVector(indices=qi, values=qv), using=SPARSE, limit=k, with_payload=True)
    return [Hit(id=p.payload["sid"], score=float(p.score), payload=p.payload) for p in res.points]

def get_many(collection: str, sids: list[str]) -> dict[str, dict]:
    if not sids:
        return {}
    recs = client().retrieve(collection, ids=[_pid(s) for s in sids], with_payload=True)
    return {r.payload["sid"]: r.payload for r in recs}

def count(collection: str) -> int:
    try:
        return client().count(collection, exact=True).count
    except Exception:  # noqa: BLE001
        return 0

# --- index metadata: which embedding model built the dense vectors. A tiny separate collection (one point) so the
# API can tell at startup whether the index matches settings.embed_model and re-ingest itself if not.
META = "index_meta"
_META_ID = _pid("index_meta")
_index_meta_cache: dict | None = None

def index_meta() -> dict:
    """Payload recorded by the last full ingest: embed_model, dim, corpus_hash. Empty if never recorded."""
    global _index_meta_cache
    if _index_meta_cache is None:
        try:
            recs = client().retrieve(META, ids=[_META_ID], with_payload=True)
            _index_meta_cache = dict(recs[0].payload) if recs else {}
        except Exception:  # noqa: BLE001 — collection missing
            _index_meta_cache = {}
    return _index_meta_cache

def index_model() -> str | None:
    return index_meta().get("embed_model") or None

def index_corpus_hash() -> str | None:
    return index_meta().get("corpus_hash") or None

def set_index_model(model: str, corpus_hash: str | None = None):
    global _index_meta_cache
    c = client()
    if not c.collection_exists(META):
        c.create_collection(META, vectors_config=qm.VectorParams(size=1, distance=qm.Distance.DOT))
    payload = {"embed_model": model, "dim": settings.embed_dim, "corpus_hash": corpus_hash}
    c.upsert(META, points=[qm.PointStruct(id=_META_ID, vector=[0.0], payload=payload)], wait=True)
    _index_meta_cache = payload

def dense_ready() -> bool:
    """False while the stored vectors come from a different model than the one used for query embeddings."""
    return index_model() == settings.embed_model
