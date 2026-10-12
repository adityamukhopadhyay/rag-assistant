"""
Build the synthetic golden set: for a stratified sample of section units, the light model writes one
specific question answerable from that section plus a short reference answer. Ground truth = the
section id (and its doc), so both pipelines are scored at the same granularity.

    .venv/bin/python -m eval.golden --n 120
"""
from __future__ import annotations
import argparse, json, random
from pathlib import Path
from rag.corpus import load_corpus, all_sections
from rag.chunking import section_units
from rag import gemini
from rag.config import settings

OUT = Path(__file__).with_name("golden_synthetic.json")

_PROMPT = """Write ONE specific question that a recruiter or engineer might ask about Aditya Mukhopadhyay which is answered by the passage below, and a concise reference answer (1–2 sentences) taken strictly from the passage. The question must be answerable ONLY from concrete content in the passage (a mechanism, a number, a decision, a tool), not generic. Do not mention "the passage".

Output JSON: {{"question": "...", "answer": "..."}}

Document: {title}
Section: {heading}
Passage:
\"\"\"
{text}
\"\"\""""

def main(n: int, seed: int = 7):
    random.seed(seed)
    units = [u for u in section_units(all_sections(load_corpus())) if len(u.text.split()) >= 40]
    # stratify: cap per document so long docs do not dominate
    by_doc: dict[str, list] = {}
    for u in units:
        by_doc.setdefault(u.doc_slug, []).append(u)
    cap = max(2, n // max(1, len(by_doc)) + 1)
    sample = []
    for slug, us in by_doc.items():
        random.shuffle(us); sample.extend(us[:cap])
    random.shuffle(sample); sample = sample[:n]
    rows = []
    for i, u in enumerate(sample):
        try:
            d = gemini.generate_json(_PROMPT.format(title=u.doc_title, heading=u.heading, text=u.text),
                                     model=settings.light_model, temperature=0.5, max_tokens=300)
            q, a = d.get("question", "").strip(), d.get("answer", "").strip()
            if len(q) < 12 or len(a) < 8:
                continue
            rows.append({"id": f"s{i:03d}", "question": q, "reference": a, "expect_sids": [u.id.split("-")[0]],
                         "expect_docs": [u.doc_slug], "heading": u.heading})
        except Exception as e:  # noqa: BLE001
            print("skip", u.id, type(e).__name__)
        if (i + 1) % 20 == 0:
            print(f"{i+1}/{len(sample)} → {len(rows)} questions")
    OUT.write_text(json.dumps(rows, indent=1, ensure_ascii=False))
    print(f"wrote {OUT.name}: {len(rows)} questions across {len({r['expect_docs'][0] for r in rows})} docs")

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--n", type=int, default=120)
    main(ap.parse_args().n)
