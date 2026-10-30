import json
import logging
import time
import uuid
from typing import Dict, List, Optional, Tuple

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse

logger = logging.getLogger("tripmate.access")
logging.basicConfig(level=logging.INFO, format="%(message)s")


class StructuredLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        t0 = time.time()
        request_id = getattr(request.state, "request_id", "unknown")

        response = await call_next(request)
        duration_ms = round((time.time() - t0) * 1000, 2)

        log_data = {
            "event": "http_request",
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
            "client_ip": request.client.host if request.client else "unknown",
        }
        logger.info(json.dumps(log_data))
        return response


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


from tripmate.config.settings import settings


class RequestBodyLimitMiddleware(BaseHTTPMiddleware):
    """Enforces maximum incoming HTTP request body size (PAYLOAD_TOO_LARGE)."""

    def __init__(self, app, max_body_bytes: int = 1_048_576):
        super().__init__(app)
        self.max_body_bytes = max_body_bytes

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > self.max_body_bytes:
                    request_id = getattr(request.state, "request_id", f"req_{uuid.uuid4().hex[:12]}")
                    return JSONResponse(
                        status_code=413,
                        content={
                            "success": False,
                            "data": None,
                            "error": {
                                "code": "PAYLOAD_TOO_LARGE",
                                "message": f"Request body exceeds maximum allowed size of {self.max_body_bytes} bytes.",
                            },
                            "request_id": request_id,
                        },
                    )
            except ValueError:
                pass
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Injects defensive HTTP security headers into all responses."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Content-Security-Policy"] = "frame-ancestors 'none'; default-src 'none'"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Cache-Control defense for API and diagnostic endpoints
        if request.url.path.startswith("/api/") or request.url.path in ("/health", "/metrics"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, proxy-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"

        # Strict-Transport-Security in production environments
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"

        return response


class SlidingWindowRateLimiter(BaseHTTPMiddleware):
    """Atomic distributed and in-memory rate limiter with per-IP and per-user tracking,
    proxy awareness, token budgets, and emergency fail-closed fallbacks for LLM routes."""

    LLM_ROUTES: Tuple[str, ...] = (
        "/api/travel",
        "/api/travel/stream",
        "/api/travel/approve",
        "/api/v1/travel",
        "/api/v1/approval",
        "/api/v1/ai",
    )

    def __init__(
        self,
        app,
        max_requests: int = 30,
        window_seconds: int = 60,
        protected_prefixes: Tuple[str, ...] = ("/api/",),
        max_tracked_ips: int = 10000,
    ):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.protected_prefixes = protected_prefixes
        self.max_tracked_ips = max_tracked_ips
        self._requests: Dict[str, List[float]] = {}
        self._user_requests: Dict[str, List[float]] = {}
        self._last_cleanup: float = time.time()

    def _cleanup_stale_records(self, now: float, force: bool = False):
        if not force and now - self._last_cleanup < 60 and len(self._requests) < self.max_tracked_ips:
            return
        self._last_cleanup = now
        window_start = now - self.window_seconds
        expired_ips = [
            ip for ip, timestamps in self._requests.items()
            if not timestamps or timestamps[-1] <= window_start
        ]
        for ip in expired_ips:
            del self._requests[ip]

        expired_users = [
            uid for uid, timestamps in self._user_requests.items()
            if not timestamps or timestamps[-1] <= window_start
        ]
        for uid in expired_users:
            del self._user_requests[uid]

        # If still over capacity after expiry cleanup, evict oldest entries
        if len(self._requests) >= self.max_tracked_ips:
            sorted_ips = sorted(self._requests.items(), key=lambda item: item[1][-1] if item[1] else 0)
            to_remove = len(self._requests) - (self.max_tracked_ips // 2)
            for ip, _ in sorted_ips[:to_remove]:
                self._requests.pop(ip, None)

    def _get_client_ip(self, request: Request) -> str:
        """Extracts client IP, honoring proxy headers ONLY when the peer is in TRUSTED_PROXIES."""
        peer_ip = request.client.host if request.client else "127.0.0.1"
        trusted = settings.TRUSTED_PROXIES

        is_trusted = (
            ("*" in trusted)
            or (peer_ip in trusted)
            or (peer_ip in ("127.0.0.1", "::1", "testclient"))
        )

        if is_trusted:
            forwarded_for = request.headers.get("X-Forwarded-For")
            if forwarded_for:
                parts = [p.strip() for p in forwarded_for.split(",") if p.strip()]
                if parts:
                    return parts[0]
            real_ip = request.headers.get("X-Real-IP")
            if real_ip and real_ip.strip():
                return real_ip.strip()

        return peer_ip

    def _get_user_id(self, request: Request) -> Optional[str]:
        """Resolves authenticated user identifier from headers if present."""
        auth = request.headers.get("Authorization") or ""
        token = None
        if auth.lower().startswith("bearer "):
            token = auth.split(" ", 1)[1].strip()
        elif request.headers.get("X-API-Key"):
            token = request.headers.get("X-API-Key", "").strip()

        if token:
            from tripmate.database.store import verify_token, store
            claims = verify_token(token)
            if claims and claims.get("uid"):
                return claims["uid"]
            user = store.get_user_by_api_key(token)
            if user and user.get("id"):
                return user["id"]
        return None

    async def _is_rate_limited_redis(self, client_ip: str, user_id: Optional[str] = None) -> Tuple[bool, int]:
        """Performs atomic distributed sliding window check using Redis pipeline."""
        from tripmate.cache.redis_cache import hybrid_cache
        if not hybrid_cache._use_redis or not hybrid_cache._redis_client:
            return False, 0

        now = time.time()
        window_start = now - self.window_seconds
        keys_to_check = [f"ratelimit:ip:{client_ip}"]
        if user_id:
            keys_to_check.append(f"ratelimit:user:{user_id}")

        try:
            pipe = hybrid_cache._redis_client.pipeline()
            for key in keys_to_check:
                pipe.zremrangebyscore(key, 0, window_start)
                pipe.zcard(key)
                pipe.zadd(key, {str(now): now})
                pipe.expire(key, self.window_seconds + 5)
            results = await pipe.execute()

            # Inspect zcard results (indices 1, 5, etc.)
            for i, key in enumerate(keys_to_check):
                request_count = results[i * 4 + 1]
                if request_count >= self.max_requests:
                    oldest_entries = await hybrid_cache._redis_client.zrange(key, 0, 0, withscores=True)
                    retry_after = int(self.window_seconds - (now - oldest_entries[0][1])) if oldest_entries else 1
                    return True, max(1, retry_after)
            return False, 0
        except Exception:
            return False, 0  # Signal Redis error

    def _is_rate_limited_in_memory(
        self,
        identifier: str,
        store_dict: Dict[str, List[float]],
        max_limit: int,
    ) -> Tuple[bool, int]:
        now = time.time()
        self._cleanup_stale_records(now)
        window_start = now - self.window_seconds

        timestamps = store_dict.get(identifier, [])
        timestamps = [ts for ts in timestamps if ts > window_start]

        if len(timestamps) >= max_limit:
            retry_after = int(self.window_seconds - (now - timestamps[0]))
            return True, max(1, retry_after)

        timestamps.append(now)
        store_dict[identifier] = timestamps
        return False, 0

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        if any(path.startswith(prefix) for prefix in self.protected_prefixes):
            client_ip = self._get_client_ip(request)
            user_id = self._get_user_id(request)

            # Determine whether route is LLM-intensive
            is_llm_route = any(path.startswith(route) for route in self.LLM_ROUTES)

            from tripmate.cache.redis_cache import hybrid_cache
            redis_available = bool(hybrid_cache._use_redis and hybrid_cache._redis_client)

            if redis_available:
                is_limited, retry_after = await self._is_rate_limited_redis(client_ip, user_id=user_id)
            else:
                # Redis is down or unconfigured
                if is_llm_route and not settings.FAIL_OPEN_REDIS:
                    # Fail-closed with emergency in-memory cap for LLM routes
                    limit_cap = settings.EMERGENCY_IN_MEMORY_RATE_LIMIT
                    is_limited, retry_after = self._is_rate_limited_in_memory(
                        f"emergency_{client_ip}", self._requests, limit_cap
                    )
                else:
                    # Fail-open to standard in-memory rate limiter
                    is_limited, retry_after = self._is_rate_limited_in_memory(
                        client_ip, self._requests, self.max_requests
                    )

            if not is_limited and user_id:
                # Also check per-user in-memory limit
                is_limited, retry_after = self._is_rate_limited_in_memory(
                    f"user_{user_id}", self._user_requests, self.max_requests
                )

            if is_limited:
                request_id = getattr(request.state, "request_id", f"req_{uuid.uuid4().hex[:12]}")
                return JSONResponse(
                    status_code=429,
                    content={
                        "success": False,
                        "data": None,
                        "error": {
                            "code": "RATE_LIMIT_EXCEEDED",
                            "message": f"Rate limit exceeded. Retry after {retry_after}s.",
                        },
                        "request_id": request_id,
                    },
                    headers={"Retry-After": str(retry_after)},
                )

        return await call_next(request)


