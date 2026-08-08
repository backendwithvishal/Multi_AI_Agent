import asyncio
import hashlib
import json
import time
from typing import Any, Callable, Dict, Optional, Tuple


class AsyncTTLCache:
    """
    High-performance Async In-Memory TTL Cache with hit/miss statistics.
    Designed for caching expensive MCP tools and external search operations.
    """

    def __init__(self, default_ttl_seconds: int = 3600):
        self._default_ttl = default_ttl_seconds
        self._store: Dict[str, Tuple[float, Any]] = {}
        self._lock = asyncio.Lock()
        self._hits = 0
        self._misses = 0

    def _hash_key(self, namespace: str, key_data: Any) -> str:
        serialized = json.dumps(key_data, sort_keys=True, default=str)
        hash_digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        return f"{namespace}:{hash_digest[:16]}"

    async def get(self, namespace: str, key_data: Any) -> Optional[Any]:
        cache_key = self._hash_key(namespace, key_data)
        async with self._lock:
            if cache_key in self._store:
                expires_at, val = self._store[cache_key]
                if time.time() < expires_at:
                    self._hits += 1
                    return val
                # Expired
                del self._store[cache_key]
            self._misses += 1
            return None

    async def set(self, namespace: str, key_data: Any, value: Any, ttl_seconds: Optional[int] = None) -> None:
        cache_key = self._hash_key(namespace, key_data)
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        expires_at = time.time() + ttl
        async with self._lock:
            self._store[cache_key] = (expires_at, value)

    async def get_or_set(
        self,
        namespace: str,
        key_data: Any,
        coro_func: Callable[[], Any],
        ttl_seconds: Optional[int] = None,
    ) -> Any:
        cached = await self.get(namespace, key_data)
        if cached is not None:
            return cached

        # Execute coroutine
        if asyncio.iscoroutinefunction(coro_func):
            val = await coro_func()
        else:
            val = coro_func()

        if val is not None:
            await self.set(namespace, key_data, val, ttl_seconds)
        return val

    async def clear(self) -> None:
        async with self._lock:
            self._store.clear()
            self._hits = 0
            self._misses = 0

    def get_stats(self) -> Dict[str, Any]:
        total = self._hits + self._misses
        hit_rate = (self._hits / total) if total > 0 else 0.0
        return {
            "cached_entries": len(self._store),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate_pct": round(hit_rate * 100, 2),
        }


# Global cache instance for backend MCP calls
mcp_cache = AsyncTTLCache(default_ttl_seconds=3600)
