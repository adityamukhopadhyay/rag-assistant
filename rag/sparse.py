"""
BM25-style sparse encoder for Qdrant sparse vectors. No model download, no external service.

Term → stable 32-bit id via hashing; value → BM25 term-frequency saturation. Qdrant applies the IDF
server-side (SparseVectorParams(modifier=IDF)), so documents and queries are encoded the same way and
the collection stays self-contained. Technical tokens (pgvector, HDBSCAN, AiSensy) survive intact,
which is exactly where lexical matching beats dense embeddings on this corpus.
"""
from __future__ import annotations
import re, zlib
from collections import Counter

_TOKEN = re.compile(r"[a-z0-9][a-z0-9_+.#-]*")
_STOP = set("""a an and are as at be but by for from has have if in into is it its of on or that the their
there these this to was were will with your you we our i he she they them his her not no yes can could
would should about after before over under than then also more most such which who whom what when where
why how all any each every some both either neither""".split())

def tokenize(text: str) -> list[str]:
    toks = _TOKEN.findall(text.lower())
    out = []
    for t in toks:
        t = t.strip(".-_")
        if len(t) < 2 or t in _STOP:
            continue
        # light stemming: plural / -ing / -ed on longer words
        if len(t) > 5:
            for suf in ("ing", "ies", "ed", "es", "s"):
                if t.endswith(suf) and len(t) - len(suf) >= 4:
                    t = t[:-len(suf)] + ("y" if suf == "ies" else "")
                    break
        out.append(t)
    return out

def term_id(term: str) -> int:
    return zlib.crc32(term.encode("utf-8")) & 0x7FFFFFFF

def encode(text: str, k1: float = 1.2, b: float = 0.75, avg_len: float = 180.0) -> tuple[list[int], list[float]]:
    toks = tokenize(text)
    if not toks:
        return [], []
    L = len(toks)
    tf = Counter(toks)
    ids, vals = [], []
    for t, f in tf.items():
        w = (f * (k1 + 1)) / (f + k1 * (1 - b + b * L / avg_len))
        ids.append(term_id(t)); vals.append(float(w))
    # Qdrant wants unique, sorted indices
    pairs = sorted(zip(ids, vals))
    return [p[0] for p in pairs], [p[1] for p in pairs]

def encode_query(text: str) -> tuple[list[int], list[float]]:
    toks = tokenize(text)
    if not toks:
        return [], []
    tf = Counter(toks)
    pairs = sorted((term_id(t), float(f)) for t, f in tf.items())
    return [p[0] for p in pairs], [p[1] for p in pairs]
