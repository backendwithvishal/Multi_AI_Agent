import time
import uuid
from typing import Dict, List, Tuple
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse


class RequestCorrelationMiddleware(BaseHTTPMiddleware):
    """
    Attaches a unique X-Request-ID header to every incoming HTTP request and response
    for backend request tracing and observability.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"
        request.state.request_id = request_id
        
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class SlidingWindowRateLimiterMiddleware(BaseHTTPMiddleware):
    """
    Sliding window rate limiter middleware protecting API routes against abuse.
    """

    def __init__(
        self,
        app,
        max_requests: int = 30,
        window_seconds: int = 60,
        protected_paths: Tuple[str, ...] = ("/api/travel",),
    ):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.protected_paths = protected_paths
        # Map of IP -> list of timestamps
        self._requests: Dict[str, List[float]] = {}

    def _is_rate_limited(self, client_ip: str) -> Tuple[bool, int]:
        now = time.time()
        window_start = now - self.window_seconds
        
        timestamps = self._requests.get(client_ip, [])
        # Filter out timestamps outside current sliding window
        timestamps = [ts for ts in timestamps if ts > window_start]
        
        if len(timestamps) >= self.max_requests:
            retry_after = int(self.window_seconds - (now - timestamps[0]))
            return True, max(1, retry_after)
            
        timestamps.append(now)
        self._requests[client_ip] = timestamps
        return False, 0

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        if any(path.startswith(prefix) for prefix in self.protected_paths):
            client_ip = request.client.host if request.client else "127.0.0.1"
            is_limited, retry_after = self._is_rate_limited(client_ip)
            
            if is_limited:
                return JSONResponse(
                    status_code=429,
                    content={
                        "success": False,
                        "error": "Too Many Requests",
                        "message": f"Rate limit of {self.max_requests} requests/min exceeded. Retry after {retry_after} seconds.",
                        "retry_after_seconds": retry_after,
                    },
                    headers={"Retry-After": str(retry_after)},
                )

        return await call_next(request)
