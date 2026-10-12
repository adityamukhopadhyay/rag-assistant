"""
"Who's asking?" — entirely optional self-identification.

A visitor may share any of name / email / phone / company. Nothing is required, nothing is verified, and a visitor who
shares nothing is never blocked or nagged twice (the UI asks once and remembers the dismissal).

Stored append-only at VISITOR_LOG (a Railway volume in production) and held in memory so the question log can stamp
each question with whoever the visitor said they were. Same 7-day retention as the question log.
"""
from __future__ import annotations
import json, os, re, threading
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter()
IST = ZoneInfo("Asia/Kolkata")
PATH = os.environ.get("VISITOR_LOG", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".cache", "visitors.jsonl"))
RETENTION_DAYS = int(os.environ.get("QUESTION_LOG_DAYS", "7"))
_lock = threading.Lock()
_by_uid: dict[str, dict] = {}
_loaded = False

class IdentifyIn(BaseModel):
    name: str | None = Field(None, max_length=80)
    email: str | None = Field(None, max_length=120)
    phone: str | None = Field(None, max_length=32)
    company: str | None = Field(None, max_length=80)
    note: str | None = Field(None, max_length=300)

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
_PHONE = re.compile(r"^[+()\d][\d\s()-]{5,}$")

def _clean(v: IdentifyIn) -> dict:
    out: dict[str, str] = {}
    for k in ("name", "company", "note"):
        s = (getattr(v, k) or "").strip()
        if s and not re.search(r"https?://", s):
            out[k] = s
    e = (v.email or "").strip()
    if e:
        if not _EMAIL.match(e):
            raise HTTPException(400, "that doesn't look like an email address")
        out["email"] = e
    p = (v.phone or "").strip()
    if p:
        if not _PHONE.match(p):
            raise HTTPException(400, "that doesn't look like a phone number")
        out["phone"] = p
    return out

def _load():
    global _loaded
    if _loaded:
        return
    _loaded = True
    if not os.path.exists(PATH):
        return
    try:
        with open(PATH, encoding="utf-8") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                    _by_uid[r["uid"]] = r
                except json.JSONDecodeError:
                    continue
    except Exception:  # noqa: BLE001
        pass

def who(uid_hash: str) -> dict | None:
    """Identity a visitor volunteered, keyed on the same hash the question log uses."""
    _load()
    r = _by_uid.get(uid_hash)
    if not r:
        return None
    return {k: v for k, v in r.items() if k in ("name", "email", "phone", "company")} or None

def save(uid_hash: str, fields: dict) -> dict:
    _load()
    row = {"uid": uid_hash, "ts": datetime.now(IST).isoformat(timespec="seconds"), **fields}
    _by_uid[uid_hash] = row
    try:
        os.makedirs(os.path.dirname(PATH), exist_ok=True)
        with _lock, open(PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001
        pass
    return row

def read(days: int = RETENTION_DAYS) -> list[dict]:
    _load()
    cut = (datetime.now(IST) - timedelta(days=days)).isoformat()
    return [r for r in _by_uid.values() if r.get("ts", "") >= cut]

@router.post("/identify")
async def identify(req: Request, body: IdentifyIn):
    from .main import _user_id
    from rag.qlog import _uid_hash, stamp_identity
    fields = _clean(body)
    if not fields:
        raise HTTPException(400, "nothing to save")
    uid = _uid_hash(_user_id(req))
    row = save(uid, fields)
    stamp_identity(uid, fields)           # backfill this visitor's earlier questions
    return {"ok": True, "saved": {k: v for k, v in row.items() if k not in ("uid", "ts")}}

@router.get("/identify")
async def get_identity(req: Request):
    from .main import _user_id
    from rag.qlog import _uid_hash
    return {"who": who(_uid_hash(_user_id(req)))}
