"""
Redaction applied to every corpus string before it is written. Pattern-based, plus a denylist
file (scripts/redact_terms.txt, one term per line, case-insensitive) for names and internal words
that patterns cannot catch. Aditya's own public contact details are allow-listed.

The chatbot serves whatever survives this file to the public internet. When in doubt, add a term.
"""
from __future__ import annotations
import re
from pathlib import Path

ALLOW_EMAILS = {"adul.m.2003@gmail.com"}
ALLOW_PHONES = {"+91-9981861975", "+91 9981861975", "9981861975"}

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(r"(?<!\d)(?:\+91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?!\d)")
_SECRET = re.compile(r"(?i)\b(?:sk|key|token|secret|bearer|api[_-]?key|password|pwd)\b\s*[:=]\s*\S+")
_LONG_HEX = re.compile(r"\b[0-9a-f]{32,}\b")
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")
_INTERNAL_HOST = re.compile(
    r"(?i)\b(?:[a-z0-9-]+\.)*(?:railway\.internal|supabase\.co|up\.railway\.app|amazonaws\.com|"
    r"db-r1\.badho\.in|waha\.badho\.in|app\.badho\.in)\b(?:[:/][^\s)\]]*)?"
)
_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

def _terms() -> list[str]:
    p = Path(__file__).with_name("redact_terms.txt")
    if not p.exists():
        return []
    return [t.strip() for t in p.read_text(encoding="utf-8").splitlines()
            if t.strip() and not t.startswith("#")]

def redact(text: str) -> str:
    text = _JWT.sub("[redacted-token]", text)
    text = _SECRET.sub(lambda m: m.group(0).split(m.group(0).split()[0])[0] + "[redacted]", text)
    text = _LONG_HEX.sub("[redacted-id]", text)
    text = _EMAIL.sub(lambda m: m.group(0) if m.group(0) in ALLOW_EMAILS else "[email redacted]", text)
    text = _PHONE.sub(lambda m: m.group(0) if m.group(0).strip() in ALLOW_PHONES else "[phone redacted]", text)
    text = _INTERNAL_HOST.sub("[internal host]", text)
    text = _IPV4.sub("[ip redacted]", text)
    for t in _terms():
        text = re.sub(re.escape(t), "[redacted]", text, flags=re.IGNORECASE)
    return text
