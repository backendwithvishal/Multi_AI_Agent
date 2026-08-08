"""
Redis Cache & In-Memory Hybrid Layer

Provides an async cache interface with optional Redis backend fallback:
- If REDIS_URL is configured and redis library is installed, uses Redis with single-flight locking and in-memory mirroring.
- Otherwise, falls back transparently to in-memory `BoundedAsyncTTLCache`.
"""

import asyncio
import inspect
import json
import os
from typing import Any, Callable, Dict, Optional
from tripmate.cache.ttl_cache import app_cache, BoundedAsyncTTLCache

try:
    import redis.asyncio as aioredis  # type: ignore[import-untyped,import-not-found]
except ImportError:
    try:
        import redis  # type: ignore[import-untyped,import-not-found]
        aioredis = getattr(redis, "asyncio", None)
    except ImportError:
        aioredis = None  # type: ignore[assignment]


class RedisHybridCache:
    """Hybrid cache abstraction with automatic fallback to bounded in-memory TTL cache."""

    def __init__(self, fallback_cache: Optional[BoundedAsyncTTLCache] = None):
        self.redis_url = os.getenv("REDIS_URL", "").strip()
        self._redis_client = None
        self._use_redis = False
        self.in_memory = fallback_cache or app_cache

        if self.redis_url and aioredis is not None:
            try:
                self._redis_client = aioredis.from_url(self.redis_url, decode_responses=True)
                self._use_redis = True
                print("[Cache] Redis Hybrid Cache initialized with active REDIS_URL.")
            except Exception as exc:
                print(f"[Cache] Redis connection failed ({exc}). Falling back to BoundedAsyncTTLCache.")
        elif self.redis_url and aioredis is None:
            print("[Cache] redis package not installed. Falling back to BoundedAsyncTTLCache.")

    async def get(self, namespace: str, key_data: Any) -> Optional[Any]:
        """Fetches value from Redis or fallback in-memory cache."""
        if self._use_redis and self._redis_client:
            try:
                cache_key = self.in_memory._hash_key(namespace, key_data)
                val = await self._redis_client.get(cache_key)
                if val is not None:
                    try:
                        return json.loads(val)
                    except Exception:
                        return val
            except Exception:
                pass
        return await self.in_memory.get(namespace, key_data)

    async def set(self, namespace: str, key_data: Any, value: Any, ttl_seconds: Optional[int] = None) -> None:
        """Stores value in both Redis and in-memory cache."""
        await self.in_memory.set(namespace, key_data, value, ttl_seconds)
        if self._use_redis and self._redis_client:
            try:
                cache_key = self.in_memory._hash_key(namespace, key_data)
                ttl = ttl_seconds or self.in_memory.default_ttl
                serialized = json.dumps(value, default=str) if not isinstance(value, str) else value
                await self._redis_client.set(cache_key, serialized, ex=ttl)
            except Exception:
                pass

    async def get_or_set(
        self,
        namespace: str,
        key_data: Any,
        coro_func: Callable[[], Any],
        ttl_seconds: Optional[int] = None,
    ) -> Any:
        """Single-Flight Get-or-Set returning cached value or executing coro_func once."""
        cached = await self.get(namespace, key_data)
        if cached is not None:
            return cached

        # Use in-memory single-flight lock mechanism to avoid concurrent duplicate requests
        async def _execution_wrapper():
            if asyncio.iscoroutinefunction(coro_func):
                res = await coro_func()
            else:
                res = coro_func()
                if inspect.isawaitable(res):
                    res = await res
            if res is not None and self._use_redis and self._redis_client:
                try:
                    cache_key = self.in_memory._hash_key(namespace, key_data)
                    ttl = ttl_seconds or self.in_memory.default_ttl
                    serialized = json.dumps(res, default=str) if not isinstance(res, str) else res
                    await self._redis_client.set(cache_key, serialized, ex=ttl)
                except Exception:
                    pass
            return res

        return await self.in_memory.get_or_set(namespace, key_data, _execution_wrapper, ttl_seconds)

    async def clear(self) -> None:
        """Clears both in-memory cache and Redis keys if connected."""
        await self.in_memory.clear()
        if self._use_redis and self._redis_client:
            try:
                await self._redis_client.flushdb()
            except Exception:
                pass

    def get_stats(self) -> Dict[str, Any]:
        """Returns diagnostic telemetry stats for the cache layer."""
        stats = self.in_memory.get_stats()
        stats["backend"] = "redis" if self._use_redis else "in_memory"
        return stats


# Global hybrid cache instance
hybrid_cache = RedisHybridCache()
