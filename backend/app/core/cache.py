"""
In-memory TTL + LRU Caches for ELORA Search & Validation.

Provides 4 separate caches with independent expiration policies:
  1. search_cache          — normalized RawResult lists per (source, query, limit, filters)
  2. provider_meta_cache   — provider health / metadata
  3. url_validation_cache  — Level 1/2 URL check outcomes
  4. deep_validation_cache — Level 3 content verification outcomes

Zero external dependencies; async/thread-safe via threading.RLock.
"""
import time
import threading
from collections import OrderedDict
from typing import Any, Dict, Generic, Optional, TypeVar

T = TypeVar("T")


class TTLCache(Generic[T]):
    """Bounded LRU cache with per-entry TTL expiration and hit/miss metrics."""

    def __init__(self, name: str, max_size: int = 256, default_ttl: int = 300):
        self.name = name
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._store: OrderedDict[str, tuple[float, T]] = OrderedDict()
        self._lock = threading.RLock()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Optional[T]:
        now = time.monotonic()
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self.misses += 1
                return None
            expires_at, value = entry
            if now >= expires_at:
                del self._store[key]
                self.misses += 1
                return None
            self._store.move_to_end(key)
            self.hits += 1
            return value

    def set(self, key: str, value: T, ttl: Optional[int] = None) -> None:
        expires_at = time.monotonic() + (ttl if ttl is not None else self.default_ttl)
        with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
            self._store[key] = (expires_at, value)
            while len(self._store) > self.max_size:
                self._store.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            self.hits = 0
            self.misses = 0

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            total = self.hits + self.misses
            return {
                "name": self.name,
                "size": len(self._store),
                "max_size": self.max_size,
                "ttl_seconds": self.default_ttl,
                "hits": self.hits,
                "misses": self.misses,
                "hit_rate": round(self.hits / total, 4) if total > 0 else 0.0,
            }


# ── Six Separate Caches ───────────────────────────────────────────────────────
search_cache: TTLCache[list] = TTLCache("search_results", max_size=512, default_ttl=300)
provider_meta_cache: TTLCache[dict] = TTLCache("provider_metadata", max_size=128, default_ttl=300)
url_validation_cache: TTLCache[dict] = TTLCache("url_validation", max_size=2048, default_ttl=1800)
deep_validation_cache: TTLCache[dict] = TTLCache("deep_validation", max_size=512, default_ttl=3600)
query_analysis_cache: TTLCache[Any] = TTLCache("query_analysis", max_size=512, default_ttl=1800)
fingerprint_cache: TTLCache[str] = TTLCache("duplicate_fingerprints", max_size=4096, default_ttl=1800)


def get_all_cache_stats() -> Dict[str, Any]:
    return {
        "search_cache": search_cache.stats(),
        "provider_meta_cache": provider_meta_cache.stats(),
        "url_validation_cache": url_validation_cache.stats(),
        "deep_validation_cache": deep_validation_cache.stats(),
        "query_analysis_cache": query_analysis_cache.stats(),
        "fingerprint_cache": fingerprint_cache.stats(),
    }


def clear_all_caches() -> None:
    search_cache.clear()
    provider_meta_cache.clear()
    url_validation_cache.clear()
    deep_validation_cache.clear()
    query_analysis_cache.clear()
    fingerprint_cache.clear()
