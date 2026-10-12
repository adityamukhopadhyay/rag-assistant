"""
"Let's connect" — a visitor books a 30-minute call; Aditya gets an email immediately.

POST /book  {name, email, date: "YYYY-MM-DD", time: "HH:MM", tz: "Asia/Kolkata", note?}
  → {ok, when: {...}, calendar_url}

Delivery providers (BOOKING_PROVIDER):
  formsubmit  (default) — no account, no key. POSTs to formsubmit.co/ajax/<BOOKING_TO_EMAIL>; the very first
              submission triggers a one-time activation email to that address, after which mail flows.
  resend      — RESEND_API_KEY; sends from onboarding@resend.dev (free tier delivers to the account owner).
  web3forms   — WEB3FORMS_KEY (free access key emailed by web3forms.com to BOOKING_TO_EMAIL; no account).
  smtp        — SMTP_HOST/PORT/USER/PASSWORD (e.g. Gmail app password).
Every booking is also appended to BOOKING_LOG (JSONL) so nothing is lost if delivery fails.
"""
from __future__ import annotations
import json, os, re, smtplib, time, urllib.parse
from datetime import datetime, timedelta
from email.message import EmailMessage
from zoneinfo import ZoneInfo
import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from rag.config import settings

router = APIRouter()
LOG = os.environ.get("BOOKING_LOG", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".cache", "bookings.jsonl"))
TO = os.environ.get("BOOKING_TO_EMAIL", "adul.m.2003@gmail.com")
PROVIDER = os.environ.get("BOOKING_PROVIDER", "formsubmit").lower()
DURATION_MIN = 30
IST = ZoneInfo("Asia/Kolkata")

class BookIn(BaseModel):
    name: str = Field(..., min_length=2, max_length=80)
    email: EmailStr
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    tz: str = Field("Asia/Kolkata", max_length=64)
    note: str | None = Field(None, max_length=600)
    company: str | None = Field(None, max_length=80)

# --- tiny per-visitor limiter for bookings (separate from the question quota)
_recent: dict[str, list[float]] = {}
def _limit(uid: str, per_day: int = 3, per_min: int = 1):
    now = time.time(); q = [t for t in _recent.get(uid, []) if now - t < 86400]
    if len(q) >= per_day or any(now - t < 60 for t in q):
        raise HTTPException(429, "That's a few requests in a row — if you didn't get a confirmation, email adul.m.2003@gmail.com directly.")
    q.append(now); _recent[uid] = q

def _when(b: BookIn) -> dict:
    try:
        tz = ZoneInfo(b.tz)
    except Exception:  # noqa: BLE001
        tz = IST
    try:
        start = datetime.strptime(f"{b.date} {b.time}", "%Y-%m-%d %H:%M").replace(tzinfo=tz)
    except ValueError:
        raise HTTPException(400, "invalid date or time")
    if start < datetime.now(tz) - timedelta(minutes=5):
        raise HTTPException(400, "that time is in the past")
    end = start + timedelta(minutes=DURATION_MIN)
    ist = start.astimezone(IST)
    return {"start": start.isoformat(), "end": end.isoformat(), "tz": str(tz),
            "day": start.strftime("%A"), "local": start.strftime("%a, %d %b %Y · %H:%M"),
            "ist": ist.strftime("%a, %d %b %Y · %H:%M IST"), "utc_start": start.astimezone(ZoneInfo("UTC")).strftime("%Y%m%dT%H%M%SZ"),
            "utc_end": end.astimezone(ZoneInfo("UTC")).strftime("%Y%m%dT%H%M%SZ")}

def _gcal(b: BookIn, w: dict) -> str:
    q = {"action": "TEMPLATE", "text": f"Call: {b.name} × Aditya Mukhopadhyay", "dates": f"{w['utc_start']}/{w['utc_end']}",
         "details": (b.note or "Intro call booked via adityamukhopadhyay.vercel.app/ask") + f"\n\nAditya: {TO}", "add": TO}
    return "https://calendar.google.com/calendar/render?" + urllib.parse.urlencode(q)

def _body(b: BookIn, w: dict, cal: str) -> str:
    return (f"New call request from your portfolio.\n\n"
            f"Who:     {b.name} <{b.email}>" + (f" · {b.company}" if b.company else "") + "\n"
            f"When:    {w['local']} ({w['tz']})\n"
            f"         = {w['ist']}\n"
            f"Length:  {DURATION_MIN} min\n"
            f"Note:    {b.note or '—'}\n\n"
            f"Add to Google Calendar: {cal}\n"
            f"Reply to: {b.email}\n")

def _send(b: BookIn, w: dict, cal: str) -> dict:
    subject = f"Call request · {b.name} · {w['ist']}"
    body = _body(b, w, cal)
    if PROVIDER == "resend":
        r = httpx.post("https://api.resend.com/emails", timeout=20,
                       headers={"Authorization": f"Bearer {os.environ.get('RESEND_API_KEY','')}"},
                       json={"from": "Ask-about-Aditya <onboarding@resend.dev>", "to": [TO], "reply_to": str(b.email), "subject": subject, "text": body})
        return {"provider": "resend", "status": r.status_code, "ok": r.status_code < 300, "detail": r.text[:200]}
    if PROVIDER == "web3forms":
        r = httpx.post("https://api.web3forms.com/submit", timeout=20, headers={"Accept": "application/json"},
                       json={"access_key": os.environ.get("WEB3FORMS_KEY", ""), "subject": subject, "from_name": "Ask-about-Aditya",
                             "replyto": str(b.email), "name": b.name, "email": str(b.email), "message": body})
        try: d = r.json()
        except Exception: d = {"raw": r.text[:200]}  # noqa: BLE001
        return {"provider": "web3forms", "status": r.status_code, "ok": r.status_code < 300 and bool(d.get("success")), "detail": d.get("message") or d}
    if PROVIDER == "smtp":
        m = EmailMessage(); m["From"] = os.environ.get("SMTP_USER", TO); m["To"] = TO; m["Reply-To"] = str(b.email); m["Subject"] = subject; m.set_content(body)
        with smtplib.SMTP(os.environ.get("SMTP_HOST", "smtp.gmail.com"), int(os.environ.get("SMTP_PORT", "587")), timeout=20) as s:
            s.starttls(); s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"]); s.send_message(m)
        return {"provider": "smtp", "ok": True}
    # formsubmit (default)
    site = (settings.cors_origins.split(",")[0].strip() or "https://adityamukhopadhyay.vercel.app")
    r = httpx.post(f"https://formsubmit.co/ajax/{TO}", timeout=20,
                   headers={"Accept": "application/json", "Content-Type": "application/json", "Origin": site, "Referer": site + "/ask",
                            "User-Agent": "Mozilla/5.0 (portfolio-rag booking)"},
                   json={"_subject": subject, "_replyto": str(b.email), "_template": "box",
                         "Who": f"{b.name} <{b.email}>" + (f" · {b.company}" if b.company else ""),
                         "When (visitor)": f"{w['local']} ({w['tz']})", "When (IST)": w["ist"], "Length": f"{DURATION_MIN} min",
                         "Note": b.note or "—", "Add to Google Calendar": cal})
    try:
        d = r.json()
    except Exception:  # noqa: BLE001
        d = {"raw": r.text[:200]}
    ok = r.status_code < 300 and str(d.get("success", "")).lower() == "true"
    return {"provider": "formsubmit", "status": r.status_code, "ok": ok, "detail": d.get("message") or d}

@router.post("/book")
async def book(req: Request, b: BookIn):
    from .main import _user_id  # lazy: avoid a circular import
    _limit(_user_id(req))
    if re.search(r"https?://", (b.note or "") + b.name):
        raise HTTPException(400, "links aren't allowed in the note")
    w = _when(b); cal = _gcal(b, w)
    try:
        delivery = _send(b, w, cal)
    except Exception as e:  # noqa: BLE001
        delivery = {"provider": PROVIDER, "ok": False, "detail": type(e).__name__}
    rec = {"ts": datetime.now(IST).isoformat(timespec="seconds"), "name": b.name, "email": str(b.email), "company": b.company,
           "when": w, "note": b.note, "delivery": delivery}
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "delivered": bool(delivery.get("ok")), "when": w, "calendar_url": cal, "to": TO,
            "message": ("Booked — I'll confirm by email." if delivery.get("ok") else
                        "Request recorded. If you don't hear back within a day, email adul.m.2003@gmail.com.")}

@router.get("/book/slots")
async def slots():
    """Working-hours slots in IST that the form offers (the visitor picks in their own zone; both are emailed)."""
    return {"duration_min": DURATION_MIN, "ist_hours": ["10:00", "11:00", "12:00", "14:00", "15:00", "16:00", "17:00", "18:00", "19:00", "20:00"],
            "days_ahead": 21, "to": TO}
