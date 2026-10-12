"""Listwise reranking with the light Gemini model. One call, JSON out, falls back to the input order. Fully traced: what went in, what came out, how each passage moved."""
from __future__ import annotations
from typing import TYPE_CHECKING
from . import gemini, trace as tr
from .config import settings
if TYPE_CHECKING:
    from .pipelines import Retrieved

_PROMPT = """You are ranking passages for a question about Aditya Mukhopadhyay, an AI engineer. Rank the passages by how directly and completely they answer the question. A passage that states the specific fact asked for beats one that only mentions the topic. Prefer passages with concrete mechanisms, numbers, names and decisions over general descriptions.

Return JSON: {{"ranking": [<passage numbers, best first>], "why": {{"<n>": "<8 words on why it ranks where it does>"}}}} — include only passages that are at least somewhat relevant, at most {k}.

Question: {q}

{passages}"""

def rerank_sections(query: str, cands: list["Retrieved"], k: int, t: tr.Tracer | None = None) -> list["Retrieved"]:
    t = t or tr.current() or tr.Tracer()
    with t.step("rerank", model=settings.light_model, method="listwise LLM rerank", n_in=len(cands), k_out=k) as h:
        h["input"] = [{"n": i, "sid": c.sid, "doc": c.doc_slug, "heading": c.heading, "score_in": round(c.score, 5)} for i, c in enumerate(cands, 1)]
        if len(cands) <= k:
            h["skipped"] = True; h["output"] = [x["n"] for x in h["input"]]
            return cands
        blocks = []
        for i, c in enumerate(cands, 1):
            body = c.text if len(c.text) < 1400 else c.text[:1400] + " …"
            blocks.append(f"[{i}] {c.doc_title} › {c.heading}\n{body}")
        try:
            from .pipelines import persona_query
            data = gemini.generate_json(_PROMPT.format(q=persona_query(query), k=k, passages="\n\n".join(blocks)),
                                        model=settings.light_model, temperature=0.0, max_tokens=400)
            order = [int(x) for x in data.get("ranking", []) if str(x).isdigit()]
            why = {str(kk): str(v) for kk, v in (data.get("why") or {}).items()}
            picked, seen = [], set()
            for n in order:
                if 1 <= n <= len(cands) and n not in seen:
                    picked.append(cands[n - 1]); seen.add(n)
                if len(picked) == k:
                    break
            for i, c in enumerate(cands, 1):          # top up so we never return fewer than k
                if len(picked) == k: break
                if i not in seen: picked.append(c); seen.add(i)
            h["output"] = [cands.index(c) + 1 for c in picked]
            h["moves"] = [{"n": cands.index(c) + 1, "from": cands.index(c) + 1, "to": j + 1,
                           "delta": (cands.index(c) + 1) - (j + 1), "why": why.get(str(cands.index(c) + 1))} for j, c in enumerate(picked)]
            h["dropped"] = [i for i in range(1, len(cands) + 1) if i not in seen]
            return picked
        except Exception as e:  # noqa: BLE001
            h["error"] = type(e).__name__; h["output"] = list(range(1, k + 1))
            return cands[:k]
