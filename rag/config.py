"""Settings. Everything comes from the environment (Railway variables in prod, .env locally)."""
from __future__ import annotations
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", env_file_encoding="utf-8", extra="ignore")

    # --- Gemini
    gemini_api_key: str = ""
    embed_model: str = "gemini-embedding-2"   # 001 was capacity-throttled (intermittent 429 RESOURCE_EXHAUSTED) from 2026-10
    embed_dim: int = 768                      # MRL truncation; 768 keeps Qdrant small and fast
    answer_model: str = "gemini-3.5-flash"
    light_model: str = "gemini-3.5-flash-lite"  # rerank, query expansion, proposition extraction
    judge_model: str = "gemini-3.5-flash"

    # --- Qdrant. url empty → embedded local mode at qdrant_path (dev/eval only; prod is the Railway server)
    qdrant_url: str = ""
    qdrant_api_key: str = ""
    qdrant_path: str = str(ROOT / ".qdrant")
    collection_sections: str = "sections"
    collection_props: str = "propositions"

    # --- Serving
    active_pipeline: str = "a"                # "a" | "b" — the A/B winner is persisted here
    query_expansion: bool = False             # evaluated as a separate toggle
    public_docs: bool = False                 # serve /docs/<slug> markdown; OFF until cleared
    cors_origins: str = "https://adityamukhopadhyay.vercel.app,http://localhost:3000"
    admin_token: str = ""                     # bearer for /admin/* (full: ingest, warm, stats)
    dashboard_token: str = ""                 # read-only bearer: questions, bookings, stats (for the /personal console)
    rate_limit_per_min: int = 20
    rate_limit_per_day: int = 400             # global, protects the free tier
    rate_limit_per_user: int = 5              # uncached questions per visitor per 24 h; 0 = unlimited (local dev)
    max_query_chars: int = 1000
    cache_ttl_s: int = 6 * 3600

    # --- Retrieval knobs
    k_dense: int = 30
    k_sparse: int = 30
    k_candidates: int = 20                    # after fusion, before rerank
    k_final: int = 5                          # sections handed to the answerer
    rerank: bool = True

    corpus_dir: Path = ROOT / "corpus"

settings = Settings()
