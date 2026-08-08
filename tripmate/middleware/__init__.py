import json
import logging
import time
import uuid
from typing import Dict, List, Tuple

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


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


class SlidingWindowRateLimiter(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        max_requests: int = 30,
        window_seconds: int = 60,
        protected_prefixes: Tuple[str, ...] = ("/api/",),
    ):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.protected_prefixes = protected_prefixes
        self._requests: Dict[str, List[float]] = {}
        self._last_cleanup: float = time.time()

    def _cleanup_stale_records(self, now: float):
        if now - self._last_cleanup < 300:
            return
        self._last_cleanup = now
        window_start = now - self.window_seconds
        expired_ips = [
            ip for ip, timestamps in self._requests.items()
            if not timestamps or timestamps[-1] <= window_start
        ]
        for ip in expired_ips:
            del self._requests[ip]

    def _is_rate_limited(self, client_ip: str) -> Tuple[bool, int]:
        now = time.time()
        self._cleanup_stale_records(now)
        window_start = now - self.window_seconds

        timestamps = self._requests.get(client_ip, [])
        timestamps = [ts for ts in timestamps if ts > window_start]

        if len(timestamps) >= self.max_requests:
            retry_after = int(self.window_seconds - (now - timestamps[0]))
            return True, max(1, retry_after)

        timestamps.append(now)
        self._requests[client_ip] = timestamps
        return False, 0

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        if any(path.startswith(prefix) for prefix in self.protected_prefixes):
            client_ip = request.client.host if request.client else "127.0.0.1"
            is_limited, retry_after = self._is_rate_limited(client_ip)

            if is_limited:
                request_id = getattr(request.state, "request_id", "unknown")
                return JSONResponse(
                    status_code=429,
                    content={
                        "success": False,
                        "data": None,
                        "error": {
                            "code": "RATE_LIMIT_EXCEEDED",
                            "message": f"Rate limit of {self.max_requests} requests/min exceeded. Retry after {retry_after}s.",
                        },
                        "request_id": request_id,
                    },
                    headers={"Retry-After": str(retry_after)},
                )

        return await call_next(request)
