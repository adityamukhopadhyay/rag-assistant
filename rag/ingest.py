"""
End-to-end ingestion: corpus → (A) section units, (B) propositions → Gemini embeddings → Qdrant.
Runs on the server (POST /admin/ingest) or from the CLI. Idempotent: point ids are derived from
stable section ids, so re-running upserts in place.

    .venv/bin/python -m rag.ingest            # both collections
    .venv/bin/python -m rag.ingest --only a   # sections only
"""
from __future__ import annotations
import argparse, json, sys, time
from pathlib import Path
from .config import settings, ROOT
from .corpus import load_corpus, all_sections, corpus_hash
from .chunking import section_units, propositions_for
from . import gemini, store

def ingest(only: str | None = None, recreate: bool = False, log=print) -> dict:
    t0 = time.time()
    docs = load_corpus()
    secs = all_sections(docs)
    units = section_units(secs)
    log(f"corpus: {len(docs)} docs, {len(secs)} sections, {len(units)} A-units")
    store.ensure_collections(recreate=recreate)
    stats = {"docs": len(docs), "sections": len(secs), "units_a": len(units), "props_b": 0}

    if only in (None, "a", "both"):
        texts = [u.contextualised() for u in units]
        dense = gemini.embed(texts, task="RETRIEVAL_DOCUMENT")
        payloads = [{"doc_slug": u.doc_slug, "doc_title": u.doc_title, "heading": u.heading, "text": u.text,
                     "page_url": u.page_url, "kind": u.kind, "site_slug": u.site_slug, "order": u.order} for u in units]
        store.upsert(settings.collection_sections, [u.id for u in units], dense, texts, payloads)
        log(f"A: upserted {len(units)} section units")

    if only in (None, "b", "both"):
        cache_path = ROOT / ".cache" / "propositions.json"
        cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
        props = []
        for i, u in enumerate(units):
            key = f"{u.id}|{hash(u.text)}"
            if key in cache:
                ps = cache[key]
            else:
                ps = [p.text for p in propositions_for(u)]
                cache[key] = ps
            for j, t in enumerate(ps):
                props.append((f"{u.id}#p{j}", u, t))
            if (i + 1) % 25 == 0:
                log(f"B: propositions for {i+1}/{len(units)} units ({len(props)} so far)")
        cache_path.parent.mkdir(exist_ok=True)
        cache_path.write_text(json.dumps(cache, ensure_ascii=False))
        texts = [f"{u.doc_title}: {t}" for _, u, t in props]      # light context prefix for the embedding only
        dense = gemini.embed(texts, task="RETRIEVAL_DOCUMENT")
        payloads = [{"parent_id": u.id, "doc_slug": u.doc_slug, "doc_title": u.doc_title, "heading": u.heading,
                     "text": t, "kind": u.kind} for _, u, t in props]
        store.upsert(settings.collection_props, [pid for pid, _, _ in props], dense, [t for _, _, t in props], payloads)
        stats["props_b"] = len(props)
        log(f"B: upserted {len(props)} propositions")

    if only in (None, "both"):
        store.set_index_model(settings.embed_model, corpus_hash())   # dense search switches on only once both collections match
        log(f"index model recorded: {settings.embed_model}")

    stats["seconds"] = round(time.time() - t0, 1)
    stats["counts"] = {settings.collection_sections: store.count(settings.collection_sections),
                       settings.collection_props: store.count(settings.collection_props)}
    stats["gemini_calls"] = gemini.Usage.calls
    log(f"done in {stats['seconds']}s: {stats['counts']}")
    return stats

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["a", "b"])
    ap.add_argument("--recreate", action="store_true")
    a = ap.parse_args()
    print(json.dumps(ingest(a.only, a.recreate), indent=1))
