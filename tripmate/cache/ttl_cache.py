"""
Single-Flight Bounded Async TTL Cache

This module provides an in-memory caching engine with:
1. TTL (Time-To-Live) expiration for cached items (default 3600 seconds).
2. Maximum entry bounds (evicts oldest entries when cache is full).
3. Single-Flight locking mechanism (`_inflight` Futures) preventing duplicate simultaneous API calls for the same query.
"""

import asyncio
import hashlib
import json
import time
from typing import Any, Callable, Dict, Optional, Tuple
from tripmate.config.settings import settings


class BoundedAsyncTTLCache:
    """Thread-safe, bounded, async TTL cache with single-flight request coalescing."""

    def __init__(self, default_ttl_seconds: int = 3600, max_entries: int = 1000):
        self.default_ttl = default_ttl_seconds
        self.max_entries = max_entries
        self._store: Dict[str, Tuple[float, Any]] = {}
        self._inflight: Dict[str, asyncio.Future] = {}
        self._lock = asyncio.Lock()
        self._hits = 0
        self._misses = 0

    def _hash_key(self, namespace: str, key_data: Any) -> str:
        """Generates a deterministic 16-character SHA-256 hash key."""
        serialized = json.dumps(key_data, sort_keys=True, default=str)
        hash_digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        return f"{namespace}:{hash_digest[:16]}"

    def _evict_if_full(self, now: float):
        """Evicts expired or oldest entries if cache capacity limit is reached."""
        if len(self._store) < self.max_entries:
            return
        expired = [k for k, (exp, _) in self._store.items() if now >= exp]
        for k in expired:
            del self._store[k]
        while len(self._store) >= self.max_entries:
            oldest_key = min(self._store.keys(), key=lambda k: self._store[k][0])
            del self._store[oldest_key]

    async def get(self, namespace: str, key_data: Any) -> Optional[Any]:
        """Fetches value from cache if present and unexpired."""
        cache_key = self._hash_key(namespace, key_data)
        async with self._lock:
            if cache_key in self._store:
                expires_at, val = self._store[cache_key]
                if time.time() < expires_at:
                    self._hits += 1
                    return val
                del self._store[cache_key]
            self._misses += 1
            return None

    async def set(self, namespace: str, key_data: Any, value: Any, ttl_seconds: Optional[int] = None) -> None:
        """Stores value in cache with expiration timestamp."""
        cache_key = self._hash_key(namespace, key_data)
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl
        now = time.time()
        expires_at = now + ttl

        async with self._lock:
            self._evict_if_full(now)
            self._store[cache_key] = (expires_at, value)

    async def get_or_set(
        self,
        namespace: str,
        key_data: Any,
        coro_func: Callable[[], Any],
        ttl_seconds: Optional[int] = None,
    ) -> Any:
        """Single-Flight Get or Set: Returns cached value or executes function once for concurrent callers."""
        cached = await self.get(namespace, key_data)
        if cached is not None:
            return cached

        cache_key = self._hash_key(namespace, key_data)

        # Single-flight lock: if another task is already fetching this key, await its result
        async with self._lock:
            if cache_key in self._inflight:
                future = self._inflight[cache_key]
                return await future

            loop = asyncio.get_running_loop()
            future = loop.create_future()
            self._inflight[cache_key] = future

        try:
            if asyncio.iscoroutinefunction(coro_func):
                val = await coro_func()
            else:
                val = coro_func()

            if val is not None:
                await self.set(namespace, key_data, val, ttl_seconds)

            future.set_result(val)
            return val
        except Exception as exc:
            future.set_exception(exc)
            raise exc
        finally:
            async with self._lock:
                self._inflight.pop(cache_key, None)

    async def clear(self) -> None:
        """Clears all stored entries and metrics."""
        async with self._lock:
            self._store.clear()
            self._inflight.clear()
            self._hits = 0
            self._misses = 0

    def get_stats(self) -> Dict[str, Any]:
        """Returns cache telemetry stats (hits, misses, hit_rate_pct)."""
        total = self._hits + self._misses
        hit_rate = (self._hits / total) if total > 0 else 0.0
        return {
            "cached_entries": len(self._store),
            "max_entries": self.max_entries,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate_pct": round(hit_rate * 100, 2),
        }


# Application-wide global cache instance
app_cache = BoundedAsyncTTLCache(
    default_ttl_seconds=settings.CACHE_TTL_SECONDS,
    max_entries=settings.CACHE_MAX_ENTRIES,
)
