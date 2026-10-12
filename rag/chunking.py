"""
Two chunking strategies — the A/B variable.

  A  sections:     structure-aware, one unit per markdown section (long ones split on paragraphs),
                   embedded with a deterministic situating prefix (doc title + heading path).
  B  propositions: each section is rewritten by the light model into atomic, decontextualised
                   statements; those are embedded and retrieved, and the PARENT SECTION is what the
                   answerer reads (small-to-big). The verbatim section is always the evidence; the
                   proposition text is only the retrieval key.
"""
from __future__ import annotations
import json
from dataclasses import dataclass
from .corpus import Section, split_long
from . import gemini
from .config import settings

# ------------------------------------------------------------------ A
def section_units(sections: list[Section]) -> list[Section]:
    out: list[Section] = []
    for s in sections:
        out.extend(split_long(s, max_words=380))
    return out

# ------------------------------------------------------------------ B
@dataclass
class Proposition:
    id: str
    parent_id: str
    text: str

_PROP_PROMPT = """You turn a section of a document about Aditya Mukhopadhyay (an AI engineer) into a list of atomic, self-contained factual statements for a search index.

Rules:
- Each statement must be understandable on its own, with NO pronouns or references that depend on context. Always name the subject: say "Aditya" or the project/system name, never "he", "it", "the system", "this".
- One fact per statement. Split compound sentences. Keep numbers, names, tool names and dates exactly as written.
- Do not add anything not in the text. Do not summarise or evaluate. Do not drop the concrete technical details — tool names, mechanisms, failure modes, decisions and their reasons are the most valuable facts.
- 3 to 14 statements depending on how much the section actually says.
- Output JSON: {{"propositions": ["...", "..."]}}

Document: {doc_title}
Section: {heading}

Text:
\"\"\"
{text}
\"\"\"
"""

def propositions_for(section: Section) -> list[Proposition]:
    prompt = _PROP_PROMPT.format(doc_title=section.doc_title, heading=section.heading, text=section.text)
    try:
        data = gemini.generate_json(prompt, model=settings.light_model, temperature=0.1, max_tokens=1500)
        props = [p.strip() for p in data.get("propositions", []) if isinstance(p, str) and len(p.strip()) > 15]
    except Exception:  # noqa: BLE001 — fall back to the section's own paragraphs
        props = [p.strip() for p in section.text.split("\n\n") if len(p.split()) >= 6]
    return [Proposition(id=f"{section.id}#p{i}", parent_id=section.id, text=t) for i, t in enumerate(props)]
