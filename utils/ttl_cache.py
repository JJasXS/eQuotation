"""Process-local TTL cache with hit/miss stats (master data, API aggregation, etc.)."""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Generic, Hashable, Optional, TypeVar

T = TypeVar("T")


class TtlCache(Generic[T]):
    """Thread-safe cache: values expire after ``default_ttl_seconds``."""

    def __init__(self, default_ttl_seconds: float = 600.0) -> None:
        self._default_ttl = max(1.0, float(default_ttl_seconds))
        self._lock = threading.RLock()
        self._store: dict[Hashable, tuple[float, T]] = {}
        self.hits = 0
        self.misses = 0

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def invalidate(self, key: Hashable) -> None:
        with self._lock:
            self._store.pop(key, None)

    def get_or_load(
        self,
        key: Hashable,
        loader: Callable[[], T],
        ttl_seconds: Optional[float] = None,
    ) -> T:
        now = time.monotonic()
        ttl = float(ttl_seconds if ttl_seconds is not None else self._default_ttl)
        with self._lock:
            ent = self._store.get(key)
            if ent is not None:
                exp, val = ent
                if now < exp:
                    self.hits += 1
                    return val
                del self._store[key]
            self.misses += 1

        val = loader()
        exp = time.monotonic() + ttl
        with self._lock:
            self._store[key] = (exp, val)
        return val

    def snapshot_stats(self) -> dict[str, Any]:
        with self._lock:
            total = self.hits + self.misses
            hit_rate = (self.hits / total) if total else 0.0
            return {
                "hits": self.hits,
                "misses": self.misses,
                "hit_rate": round(hit_rate, 4),
            }


# Shared caches (single process). TTL configurable via env in callers.
sql_api_master_cache: TtlCache[Any] = TtlCache(default_ttl_seconds=600.0)
