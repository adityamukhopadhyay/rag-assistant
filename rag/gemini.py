"""Thin Gemini client: embeddings (with MRL truncation + normalisation), JSON generation, streaming. Retries on 429/5xx."""
from __future__ import annotations
import asyncio, json, math, random, re, time
from typing import AsyncIterator, Iterable
from google import genai
from google.genai import types
from .config import settings
from . import trace as _tr

_client: genai.Client | None = None

def client() -> genai.Client:
    global _client
    if _client is None:
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client

class Usage:
    """Process-wide token counter, exposed on /health and used by the daily budget guard."""
    prompt = 0; output = 0; calls = 0
    @classmethod
    def add(cls, resp):
        um = getattr(resp, "usage_metadata", None)
        if um:
            cls.prompt += um.prompt_token_count or 0
            cls.output += um.candidates_token_count or 0
        cls.calls += 1

def _retry(fn, *a, tries=5, **kw):
    delay = 1.0
    for i in range(tries):
        try:
            return fn(*a, **kw)
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            transient = any(x in msg for x in ("429", "RESOURCE_EXHAUSTED", "503", "500", "UNAVAILABLE", "deadline"))
            if not transient or i == tries - 1:
                raise
            time.sleep(delay + random.random() * 0.5); delay = min(delay * 2, 20)

def _normalise(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]

def embed(texts: list[str], task: str = "RETRIEVAL_DOCUMENT", batch: int = 64, tries: int = 5) -> list[list[float]]:
    """task: RETRIEVAL_DOCUMENT | RETRIEVAL_QUERY. Returns unit-normalised vectors of settings.embed_dim.
    `tries` caps the 429/5xx retries (5 ≈ 17 s worst case; query-time callers pass fewer and fall back to sparse)."""
    out: list[list[float]] = []
    t0 = time.perf_counter()
    for i in range(0, len(texts), batch):
        chunk = texts[i:i + batch]
        # One Content per text. gemini-embedding-2 is multimodal: a bare list of strings (or Parts) is treated as the
        # parts of ONE content and fused into a single embedding — 001 happened to split them, 2 does not.
        contents = [types.Content(parts=[types.Part(text=t)]) for t in chunk]
        resp = _retry(client().models.embed_content, model=settings.embed_model, contents=contents,
                      config=types.EmbedContentConfig(task_type=task, output_dimensionality=settings.embed_dim), tries=tries)
        Usage.calls += 1
        if len(resp.embeddings) != len(chunk):
            raise RuntimeError(f"embed: {settings.embed_model} returned {len(resp.embeddings)} vectors for {len(chunk)} texts")
        out.extend(_normalise(e.values) for e in resp.embeddings)
    if (tr := _tr.current()):
        tr.call("embed", settings.embed_model, (time.perf_counter() - t0) * 1000, texts=len(texts), task=task, dim=settings.embed_dim)
    return out

def embed_query(text: str) -> list[float]:
    return embed([text], task="RETRIEVAL_QUERY")[0]

def generate(prompt: str, *, model: str | None = None, system: str | None = None, json_mode: bool = False,
             temperature: float = 0.2, max_tokens: int = 2048) -> str:
    # Gemini 3.x thinks by default and the thoughts count against max_output_tokens — a 700-token
    # budget produced 26 answer tokens. These are grounded, short-form calls: thinking off.
    cfg = types.GenerateContentConfig(temperature=temperature, max_output_tokens=max_tokens,
                                      system_instruction=system,
                                      response_mime_type="application/json" if json_mode else None,
                                      thinking_config=types.ThinkingConfig(thinking_level="minimal"))
    t0 = time.perf_counter()
    resp = _retry(client().models.generate_content, model=model or settings.answer_model, contents=prompt, config=cfg)
    Usage.add(resp)
    if (tr := _tr.current()):
        um = getattr(resp, "usage_metadata", None)
        tr.call("generate", model or settings.answer_model, (time.perf_counter() - t0) * 1000, json=json_mode,
                prompt_tokens=getattr(um, "prompt_token_count", None), output_tokens=getattr(um, "candidates_token_count", None),
                prompt_chars=len(prompt))
    return resp.text or ""

def generate_json(prompt: str, **kw):
    txt = generate(prompt, json_mode=True, **kw)
    txt = re.sub(r"^```(?:json)?\s*|\s*```$", "", txt.strip())
    return json.loads(txt)

async def stream(prompt: str, *, model: str | None = None, system: str | None = None,
                 temperature: float = 0.3, max_tokens: int = 1024) -> AsyncIterator[str]:
    cfg = types.GenerateContentConfig(temperature=temperature, max_output_tokens=max_tokens, system_instruction=system,
                                      thinking_config=types.ThinkingConfig(thinking_level="minimal"))
    aclient = client().aio
    resp = await aclient.models.generate_content_stream(model=model or settings.answer_model, contents=prompt, config=cfg)
    async for chunk in resp:
        if chunk.text:
            yield chunk.text
        um = getattr(chunk, "usage_metadata", None)
        if um and um.candidates_token_count:
            Usage.prompt = Usage.prompt  # final chunk carries totals; keep simple
    Usage.calls += 1
