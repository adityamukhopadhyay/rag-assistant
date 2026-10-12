"""Input and output guards. Cheap, deterministic, run on every request."""
from __future__ import annotations
import re, unicodedata
from .config import settings

_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_INJECTION = re.compile(
    r"(?i)(ignore (all |the |your )?(previous|prior|above) (instructions|rules|prompt)|"
    r"you are now|new instructions:|system prompt|developer message|reveal (your|the) (prompt|instructions)|"
    r"jailbreak|DAN mode|act as an? (unrestricted|unfiltered))"
)
_PII_ASK = re.compile(r"(?i)\b(aadhaar|aadhar|pan (card|number)|passport|bank (account|details)|salary slip|home address|date of birth|dob)\b")

class Rejected(Exception):
    def __init__(self, reason: str, status: int = 400):
        super().__init__(reason); self.reason = reason; self.status = status

def clean_query(q: str) -> str:
    q = unicodedata.normalize("NFKC", q or "")
    q = _CTRL.sub("", q).strip()
    q = re.sub(r"\s+", " ", q)
    if not q:
        raise Rejected("empty question")
    if len(q) > settings.max_query_chars:
        raise Rejected(f"question too long (max {settings.max_query_chars} characters)", 413)
    return q

def classify(q: str) -> dict:
    """Flags the answerer prompt can use; nothing here blocks — the model answers, but forewarned."""
    return {"injection": bool(_INJECTION.search(q)), "pii_ask": bool(_PII_ASK.search(q))}

_OUT_PHONE = re.compile(r"(?<!\d)(?:\+91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?!\d)")
_OUT_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

def scrub_output(text: str) -> str:
    """Belt and braces: the corpus is already redacted, but never let a non-public contact through."""
    text = _OUT_EMAIL.sub(lambda m: m.group(0) if m.group(0) == "adul.m.2003@gmail.com" else "[email withheld]", text)
    text = _OUT_PHONE.sub(lambda m: m.group(0) if "9981861975" in m.group(0) else "[phone withheld]", text)
    return text
