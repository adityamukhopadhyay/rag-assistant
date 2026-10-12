"""Tiny TTL+LRU cache for full answers, keyed on the normalised question + pipeline. Saves free-tier quota on repeats."""
from __future__ import annotations
import hashlib, re, time
from collections import OrderedDict
from typing import Any
from .config import settings

class TTLCache:
    def __init__(self, maxsize: int = 500, ttl: float | None = None):
        self.maxsize = maxsize; self.ttl = ttl or settings.cache_ttl_s
        self._d: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._pinned: set[str] = set()
        self.hits = 0; self.misses = 0

    @staticmethod
    def key(query: str, pipeline: str) -> str:
        norm = re.sub(r"[^a-z0-9 ]+", "", query.lower()).strip()
        norm = re.sub(r"\s+", " ", norm)
        return hashlib.sha1(f"{pipeline}|{norm}".encode()).hexdigest()

    def get(self, k: str):
        item = self._d.get(k)
        if not item:
            self.misses += 1; return None
        ts, v = item
        if k not in self._pinned and time.time() - ts > self.ttl:
            del self._d[k]; self.misses += 1; return None
        self._d.move_to_end(k); self.hits += 1
        return v

    def put(self, k: str, v: Any, pin: bool = False):
        self._d[k] = (time.time(), v); self._d.move_to_end(k)
        if pin: self._pinned.add(k)
        while len(self._d) > self.maxsize:
            old = next(iter(self._d))
            if old in self._pinned: self._d.move_to_end(old); break
            self._d.popitem(last=False)

answers = TTLCache()
