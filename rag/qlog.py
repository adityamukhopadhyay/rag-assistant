"""
Rolling 7-day log of every question asked. Append-only JSONL on a persistent path (a Railway volume in
production: QUESTION_LOG=/data/questions.jsonl), pruned to the retention window on write.

Each row: ts (IST), question, pipeline, cached, precomputed, uid (short hash of the visitor id, never the raw id/IP),
latency_ms, answer_preview (first 240 chars), sources (doc slugs).
"""
from __future__ import annotations
import hashlib, json, os, threading, time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
PATH = os.environ.get("QUESTION_LOG", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".cache", "questions.jsonl"))
RETENTION_DAYS = int(os.environ.get("QUESTION_LOG_DAYS", "7"))
_lock = threading.Lock()
_last_prune = 0.0

def _uid_hash(uid: str) -> str:
    return hashlib.sha1(uid.encode()).hexdigest()[:10]

def record(question: str, *, pipeline: str, cached: bool, precomputed: bool, uid: str, latency_ms: float | None,
           answer: str, sources: list[str]) -> None:
    uid_h = _uid_hash(uid)
    row = {"ts": datetime.now(IST).isoformat(timespec="seconds"), "question": question[:500], "pipeline": pipeline,
           "cached": cached, "precomputed": precomputed, "uid": uid_h, "latency_ms": round(latency_ms) if latency_ms else None,
           "answer_preview": (answer or "")[:240], "sources": sources[:5]}
    try:                                  # if this visitor said who they are, record it on the question
        from api.visitors import who
        if (ident := who(uid_h)):
            row["who"] = ident
    except Exception:  # noqa: BLE001
        pass
    try:
        os.makedirs(os.path.dirname(PATH), exist_ok=True)
        with _lock:
            with open(PATH, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        _maybe_prune()
    except Exception:  # noqa: BLE001 — logging must never break answering
        pass

def _cutoff(days: int = RETENTION_DAYS) -> datetime:
    return datetime.now(IST) - timedelta(days=days)

def _maybe_prune():
    global _last_prune
    if time.time() - _last_prune < 3600:
        return
    _last_prune = time.time()
    rows = read(days=RETENTION_DAYS)
    with _lock:
        with open(PATH, "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")

def read(days: int = RETENTION_DAYS) -> list[dict]:
    if not os.path.exists(PATH):
        return []
    cut = _cutoff(days).isoformat()
    out = []
    with _lock:
        for line in open(PATH, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("ts", "") >= cut:
                out.append(r)
    return out

def stamp_identity(uid_hash: str, fields: dict) -> int:
    """Backfill the questions this visitor already asked, so a late identification is not lost."""
    rows = read(RETENTION_DAYS); n = 0
    for r in rows:
        if r.get("uid") == uid_hash:
            r["who"] = fields; n += 1
    if n:
        with _lock, open(PATH, "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return n

def summary(days: int = RETENTION_DAYS) -> dict:
    rows = read(days)
    by_day: dict[str, int] = {}; by_q: dict[str, int] = {}; uids = set(); live = 0
    for r in rows:
        by_day[r["ts"][:10]] = by_day.get(r["ts"][:10], 0) + 1
        by_q[r["question"].strip().lower()] = by_q.get(r["question"].strip().lower(), 0) + 1
        uids.add(r["uid"]); live += 0 if r.get("cached") else 1
    top = sorted(by_q.items(), key=lambda kv: -kv[1])[:15]
    known: dict[str, dict] = {}
    for r in rows:
        if r.get("who"):
            k = known.setdefault(r["uid"], {**r["who"], "questions": 0, "last": r["ts"]})
            k["questions"] += 1; k["last"] = max(k["last"], r["ts"])
    return {"days": days, "total": len(rows), "live": live, "cached": len(rows) - live, "unique_visitors": len(uids),
            "identified": len(known), "who_asked": sorted(known.values(), key=lambda x: x["last"], reverse=True),
            "by_day": dict(sorted(by_day.items())), "top_questions": [{"question": q, "count": n} for q, n in top],
            "path": PATH}
