"""
Redis Cache & In-Memory Hybrid Layer

Provides an async cache interface with optional Redis backend fallback:
- If REDIS_URL is configured and redis library is installed, uses Redis with single-flight locking and in-memory mirroring.
- Otherwise, falls back transparently to in-memory `BoundedAsyncTTLCache`.
"""

import asyncio
import hashlib
import inspect
import json
import logging
import os
from typing import Any, Callable, Dict, Optional
from tripmate.cache.ttl_cache import app_cache, BoundedAsyncTTLCache
from tripmate.config.settings import settings

logger = logging.getLogger("tripmate.cache")

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

        from tripmate.config.settings import settings
        if settings.is_test and not os.getenv("RUN_LIVE_REDIS_TESTS"):
            self._use_redis = False
            return

        if self.redis_url and aioredis is not None:
            try:
                self._redis_client = aioredis.from_url(
                    self.redis_url,
                    decode_responses=True,
                    socket_timeout=0.5,
                    socket_connect_timeout=0.5,
                )
                self._use_redis = True
                logger.info("[Cache] Redis Hybrid Cache initialized with active REDIS_URL.")
            except Exception as exc:
                logger.warning(f"[Cache] Redis connection failed ({exc}). Falling back to BoundedAsyncTTLCache.")
        elif self.redis_url and aioredis is None:
            logger.warning("[Cache] redis package not installed. Falling back to BoundedAsyncTTLCache.")

    async def get(self, namespace: str, key_data: Any) -> Optional[Any]:
        """Fetches value from Redis or fallback in-memory cache."""
        if self._use_redis and self._redis_client:
            try:
                cache_key = self.in_memory._hash_key(namespace, key_data)
                val = await asyncio.wait_for(self._redis_client.get(cache_key), timeout=0.25)
                if val is not None:
                    try:
                        from tripmate.middleware.metrics import metrics_registry
                        metrics_registry.record_cache_hit("redis")
                    except Exception:
                        pass
                    try:
                        return json.loads(val)
                    except Exception:
                        return val
                else:
                    try:
                        from tripmate.middleware.metrics import metrics_registry
                        metrics_registry.record_cache_miss("redis")
                    except Exception:
                        pass
            except Exception as exc:
                self._use_redis = False
                logger.info(f"[Cache] Redis unavailable ({exc}). Using in-memory fallback.")
        return await self.in_memory.get(namespace, key_data)

    async def set(self, namespace: str, key_data: Any, value: Any, ttl_seconds: Optional[int] = None) -> None:
        """Stores value in both Redis and in-memory cache."""
        await self.in_memory.set(namespace, key_data, value, ttl_seconds)
        if self._use_redis and self._redis_client:
            try:
                cache_key = self.in_memory._hash_key(namespace, key_data)
                ttl = ttl_seconds or self.in_memory.default_ttl
                serialized = json.dumps(value, default=str)
                await asyncio.wait_for(self._redis_client.set(cache_key, serialized, ex=ttl), timeout=0.25)
            except Exception as exc:
                self._use_redis = False
                logger.info(f"[Cache] Redis set failed ({exc}). Using in-memory fallback.")

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
                    serialized = json.dumps(res, default=str)
                    await self._redis_client.set(cache_key, serialized, ex=ttl)
                except Exception:
                    pass
            return res

        return await self.in_memory.get_or_set(namespace, key_data, _execution_wrapper, ttl_seconds)

    def _build_mcp_cache_key(self, namespace: str, query_data: Any, user_id: Optional[str] = None) -> str:
        """Constructs a tenant/user-isolated SHA-256 hashed cache key."""
        user_scope = f"u_{user_id}" if user_id else "public"
        serialized = json.dumps(query_data, sort_keys=True, default=str)
        hash_digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        return f"tripmate:mcp:{namespace}:{user_scope}:{hash_digest}"

    async def get_mcp(self, namespace: str, query_data: Any, user_id: Optional[str] = None) -> Optional[Any]:
        """Fetches cached MCP tool output with fallback protection and strict user isolation."""
        user_scope = f"u_{user_id}" if user_id else "public"
        cache_key = self._build_mcp_cache_key(namespace, query_data, user_id)
        if self._use_redis and self._redis_client:
            try:
                val = await asyncio.wait_for(self._redis_client.get(cache_key), timeout=0.25)
                if val is not None:
                    try:
                        from tripmate.middleware.metrics import metrics_registry
                        metrics_registry.record_cache_hit("redis")
                    except Exception:
                        pass
                    try:
                        return json.loads(val)
                    except Exception:
                        return val
                else:
                    try:
                        from tripmate.middleware.metrics import metrics_registry
                        metrics_registry.record_cache_miss("redis")
                    except Exception:
                        pass
            except Exception as exc:
                self._use_redis = False
                logger.info(f"[Cache] Redis get_mcp failed ({exc}). Falling back to memory.")
        return await self.in_memory.get(f"mcp:{namespace}:{user_scope}", query_data)

    async def set_mcp(
        self,
        namespace: str,
        query_data: Any,
        value: Any,
        user_id: Optional[str] = None,
        ttl_seconds: Optional[int] = None,
    ) -> bool:
        """Stores MCP output in Redis with size limits and TTL, mirroring to isolated in-memory fallback."""
        if value is None:
            return False
        serialized_val = json.dumps(value, default=str)
        val_bytes = serialized_val.encode("utf-8")
        if len(val_bytes) > settings.MCP_CACHE_MAX_BYTES:
            logger.warning(
                f"[Cache] MCP response exceeded max size ({len(val_bytes)} > {settings.MCP_CACHE_MAX_BYTES} bytes). Skipping cache."
            )
            return False

        user_scope = f"u_{user_id}" if user_id else "public"
        ttl = ttl_seconds or settings.MCP_CACHE_TTL_SECONDS
        await self.in_memory.set(f"mcp:{namespace}:{user_scope}", query_data, value, ttl)
        if self._use_redis and self._redis_client:
            try:
                cache_key = self._build_mcp_cache_key(namespace, query_data, user_id)
                await asyncio.wait_for(self._redis_client.set(cache_key, serialized_val, ex=ttl), timeout=0.25)
            except Exception as exc:
                self._use_redis = False
                logger.info(f"[Cache] Redis set_mcp failed ({exc}). Using in-memory fallback.")
        return True

    async def get_or_set_mcp(
        self,
        namespace: str,
        query_data: Any,
        coro_func: Callable[[], Any],
        user_id: Optional[str] = None,
        ttl_seconds: Optional[int] = None,
    ) -> Any:
        """Coalesced Get-or-Set for MCP responses with Redis and isolated memory fallback."""
        cached = await self.get_mcp(namespace, query_data, user_id)
        if cached is not None:
            return cached

        user_scope = f"u_{user_id}" if user_id else "public"

        async def _mcp_wrapper():
            if asyncio.iscoroutinefunction(coro_func):
                res = await coro_func()
            else:
                res = coro_func()
                if inspect.isawaitable(res):
                    res = await res
            if res is not None:
                await self.set_mcp(namespace, query_data, res, user_id, ttl_seconds)
            return res

        return await self.in_memory.get_or_set(f"mcp:{namespace}:{user_scope}", query_data, _mcp_wrapper, ttl_seconds)

    async def clear(self) -> None:
        """Clears both in-memory cache and Redis keys if connected."""
        await self.in_memory.clear()
        if self._use_redis and self._redis_client:
            try:
                await self._redis_client.flushdb()
            except Exception:
                pass

    async def aclose(self) -> None:
        """Gracefully closes Redis connection pool on server shutdown."""
        if self._use_redis and self._redis_client:
            try:
                if hasattr(self._redis_client, "aclose"):
                    await asyncio.wait_for(self._redis_client.aclose(), timeout=1.0)
                elif hasattr(self._redis_client, "close"):
                    res = self._redis_client.close()
                    if inspect.isawaitable(res):
                        await asyncio.wait_for(res, timeout=1.0)
            except Exception:
                pass

    def close(self) -> None:
        """Synchronous wrapper for closing cache resources."""
        if self._use_redis and self._redis_client:
            try:
                if hasattr(self._redis_client, "close"):
                    self._redis_client.close()
            except Exception:
                pass

    async def ping(self) -> bool:
        """Pings Redis backend or returns False if in-memory fallback."""
        if self._use_redis and self._redis_client:
            try:
                res = await asyncio.wait_for(self._redis_client.ping(), timeout=1.0)
                return bool(res)
            except Exception:
                return False
        return False

    def get_stats(self) -> Dict[str, Any]:
        """Returns diagnostic telemetry stats for the cache layer."""
        stats = self.in_memory.get_stats()
        stats["backend"] = "redis" if self._use_redis else "in_memory"
        return stats


# Global hybrid cache instance
hybrid_cache = RedisHybridCache()

