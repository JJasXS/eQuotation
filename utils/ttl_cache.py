"""Process-local TTL cache with hit/miss stats (master data, API aggregation, etc.)."""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Generic, Hashable, Optional, TypeVar

T = TypeVar("T")


class TtlCache(Generic[T]):
    """Thread-safe cache: values expire after ``default_ttl_seconds``.

    Expired entries are dropped on access and opportunistically on write.
    Concurrent misses for the same key share one loader (single-flight).
    """

    def __init__(
        self,
        default_ttl_seconds: float = 600.0,
        max_entries: int = 256,
    ) -> None:
        self._default_ttl = max(1.0, float(default_ttl_seconds))
        self._max_entries = max(8, int(max_entries))
        self._lock = threading.RLock()
        self._store: dict[Hashable, tuple[float, T]] = {}
        self._inflight: dict[Hashable, threading.Event] = {}
        self.hits = 0
        self.misses = 0
        self.evictions = 0
        self.expired_purged = 0

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def invalidate(self, key: Hashable) -> None:
        with self._lock:
            self._store.pop(key, None)

    def _purge_expired_unlocked(self, now: float) -> None:
        dead = [k for k, (exp, _) in self._store.items() if now >= exp]
        for k in dead:
            del self._store[k]
            self.expired_purged += 1

    def _evict_overflow_unlocked(self) -> None:
        while len(self._store) >= self._max_entries:
            oldest_key = min(self._store, key=lambda k: self._store[k][0])
            del self._store[oldest_key]
            self.evictions += 1

    def purge_expired(self) -> int:
        """Drop expired entries; returns how many were removed."""
        now = time.monotonic()
        with self._lock:
            before = self.expired_purged
            self._purge_expired_unlocked(now)
            return self.expired_purged - before

    def get_or_load(
        self,
        key: Hashable,
        loader: Callable[[], T],
        ttl_seconds: Optional[float] = None,
    ) -> T:
        now = time.monotonic()
        ttl = float(ttl_seconds if ttl_seconds is not None else self._default_ttl)

        with self._lock:
            self._purge_expired_unlocked(now)
            ent = self._store.get(key)
            if ent is not None and now < ent[0]:
                self.hits += 1
                return ent[1]
            if ent is not None:
                del self._store[key]
                self.expired_purged += 1

            wait_event = self._inflight.get(key)
            lead = wait_event is None
            if lead:
                wait_event = threading.Event()
                self._inflight[key] = wait_event
            self.misses += 1

        if not lead:
            wait_event.wait(timeout=max(ttl, 120.0))
            with self._lock:
                ent = self._store.get(key)
                if ent is not None and time.monotonic() < ent[0]:
                    self.hits += 1
                    return ent[1]
            # Leader failed or timed out; load ourselves.
            return self.get_or_load(key, loader, ttl_seconds=ttl)

        try:
            val = loader()
        except BaseException:
            with self._lock:
                evt = self._inflight.pop(key, None)
                if evt is not None:
                    evt.set()
            raise

        exp = time.monotonic() + ttl
        with self._lock:
            self._evict_overflow_unlocked()
            self._store[key] = (exp, val)
            evt = self._inflight.pop(key, None)
            if evt is not None:
                evt.set()
        return val

    def snapshot_stats(self) -> dict[str, Any]:
        now = time.monotonic()
        with self._lock:
            total = self.hits + self.misses
            hit_rate = (self.hits / total) if total else 0.0
            expired = sum(1 for exp, _ in self._store.values() if now >= exp)
            return {
                "hits": self.hits,
                "misses": self.misses,
                "hit_rate": round(hit_rate, 4),
                "entries": len(self._store),
                "expired_entries": expired,
                "max_entries": self._max_entries,
                "evictions": self.evictions,
                "expired_purged": self.expired_purged,
            }


# Shared caches (single process). TTL configurable via env in callers.
sql_api_master_cache: TtlCache[Any] = TtlCache(default_ttl_seconds=600.0, max_entries=256)
