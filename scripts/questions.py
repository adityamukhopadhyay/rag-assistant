#!/usr/bin/env python3
"""Print the questions asked in the last 7 days (from the live API). Reads ADMIN_TOKEN from .railway_state.json.
    .venv/bin/python scripts/questions.py            # summary + list
    .venv/bin/python scripts/questions.py --json     # raw
"""
import json, sys, httpx
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
st = json.loads((ROOT / ".railway_state.json").read_text())
API = f"https://{st['api_domain']}"
d = httpx.get(f"{API}/admin/questions", headers={"Authorization": f"Bearer {st['admin_token']}"}, timeout=30).json()
if "--json" in sys.argv:
    print(json.dumps(d, indent=1, ensure_ascii=False)); sys.exit()
s = d["summary"]
print(f"last {s['days']} days: {s['total']} questions ({s['live']} live, {s['cached']} cached) from {s['unique_visitors']} visitors, {s.get('identified', 0)} of whom said who they are")
for day, n in s["by_day"].items(): print(f"  {day}: {n}")
if s.get("who_asked"):
    print("\nwho asked:")
    for w in s["who_asked"]:
        bits = " · ".join(filter(None, [w.get("name"), w.get("company"), w.get("email"), w.get("phone")]))
        print(f"  {w['questions']:3} questions  {bits}")
print("\ntop questions:")
for t in s["top_questions"]: print(f"  {t['count']:3}  {t['question']}")
print("\nnewest:")
for r in d["questions"][:40]:
    when = "cache" if r["cached"] else f"{r['latency_ms']:>5}ms"
    who = (r.get("who") or {}).get("name") or (r.get("who") or {}).get("email") or r["uid"]
    print(f"  {r['ts'][5:16]}  {when:>7}  {who[:18]:18}  {r['question'][:60]}")
