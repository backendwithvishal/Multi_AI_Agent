import os
import re
import uuid
import uvicorn
from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI, Request, APIRouter, Depends, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError, HTTPException as FastAPIHTTPException
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator

from tripmate.config.settings import settings
from tripmate.middleware import (
    RequestIDMiddleware,
    SlidingWindowRateLimiter,
    SecurityHeadersMiddleware,
    StructuredLoggingMiddleware,
    RequestBodyLimitMiddleware,
)
from tripmate.middleware.metrics import PrometheusMetricsMiddleware
from tripmate.schemas import APIResponse, ErrorDetail, APIRootResponse, strip_control_chars
from tripmate.api.dependencies import get_current_user

# Import API Domain Routers
from tripmate.api.v1.routes.health import router as health_v1_router
from tripmate.api.v1.routes.status import router as status_v1_router
from tripmate.api.v1.routes.ai_analysis import router as ai_analysis_v1_router
from tripmate.api.v1.routes.auth import router as auth_v1_router
from tripmate.api.v1.routes.watchlists import router as watchlists_v1_router
from tripmate.api.v1.routes.alerts import router as alerts_v1_router
from tripmate.api.v1.routes.assets import router as assets_v1_router
from tripmate.api.v1.routes.financial import router as financial_v1_router
from tripmate.api.v1.routes.admin import router as admin_v1_router
from tripmate.api.v1.routes.ai import router as ai_v1_router
from tripmate.api.v1.routes.travel import router as travel_v1_router
from tripmate.api.v1.routes.approval import router as approval_v1_router
from tripmate.api.v1.routes.runs import router as runs_v1_router
from tripmate.api.v1.routes.metrics import router as metrics_v1_router
from tripmate.api.v1.routes.tasks import router as tasks_v1_router
from tripmate.api.v1.routes.booking import router as booking_v1_router
from tripmate.services.travel_service import travel_service
from tripmate.tasks import task_queue


import logging
from tripmate.cache.redis_cache import hybrid_cache

logger = logging.getLogger("tripmate.app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not settings.is_test:
        # Perform production configuration check on application startup
        try:
            settings.validate_production()
        except ValueError as exc:
            if settings.APP_ENV == "production":
                logger.error(f"[STARTUP ERROR] {exc}")
                raise
            else:
                logger.warning(f"[STARTUP WARNING] {exc}")

        # Initialize and apply database migrations if PostgreSQL is configured and accessible
        from tripmate.database import get_formatted_db_url, get_db_pool, close_db_pools
        if get_formatted_db_url():
            try:
                if get_db_pool():
                    from tripmate.database.migrator import run_migrations_up
                    from tripmate.database.store import store
                    mig_res = run_migrations_up("head")
                    if mig_res.get("success"):
                        logger.info("PostgreSQL database migrations verified and up to date.")
                    else:
                        logger.warning(f"Database migration notice on startup: {mig_res.get('error')}")
                    store._seed_initial_data()
                else:
                    logger.info("Database pool not active; skipping startup migration run.")
            except Exception as exc:
                logger.warning(f"Notice during database initialization on startup: {exc}")

        # Initialize persistent MCP client manager
        try:
            from mcp_client import mcp_manager
            await mcp_manager.startup()
        except Exception as exc:
            logger.warning(f"Notice during MCP Manager startup: {exc}")

        # Start background task queue worker
        await task_queue.start()

    yield

    if not settings.is_test:
        # Graceful shutdown hooks
        try:
            # Finish or cancel in-flight active workflow runs
            from tripmate.services.travel_service import ACTIVE_RUNS
            for task in list(ACTIVE_RUNS):
                if not task.done():
                    task.cancel()
            if ACTIVE_RUNS:
                await asyncio.gather(*[t for t in list(ACTIVE_RUNS) if not t.done()], return_exceptions=True)
                ACTIVE_RUNS.clear()

            await task_queue.stop()
            from mcp_client import mcp_manager
            await mcp_manager.shutdown()
            await hybrid_cache.aclose()
            from tripmate.database import close_checkpointer, close_db_pools
            close_checkpointer()
            close_db_pools()
        except Exception as exc:
            logger.warning(f"[SHUTDOWN WARNING] Clean shutdown: {exc}")


# Initialize FastAPI web app with conditional docs visibility in production
docs_url = "/docs" if (not settings.is_production or settings.ENABLE_DOCS_IN_PROD) else None
redoc_url = "/redoc" if (not settings.is_production or settings.ENABLE_DOCS_IN_PROD) else None
openapi_url = "/openapi.json" if (not settings.is_production or settings.ENABLE_DOCS_IN_PROD) else None

app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "Production Enterprise Multi-Agent Travel Planner Engine built with "
        "LangGraph, MCP, FastAPI, Async SSE Streaming, Sliding Window Rate Limiting, "
        "Circuit Breakers, and Human-in-the-Loop approval workflows."
    ),
    version=settings.APP_VERSION,
    docs_url=docs_url,
    redoc_url=redoc_url,
    openapi_url=openapi_url,
    lifespan=lifespan,
)

# Register HTTP middleware chain in order of execution
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestBodyLimitMiddleware, max_body_bytes=settings.MAX_REQUEST_BODY_BYTES)
app.add_middleware(PrometheusMetricsMiddleware)
app.add_middleware(StructuredLoggingMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(
    SlidingWindowRateLimiter,
    max_requests=settings.RATE_LIMIT_REQUESTS,
    window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
    protected_prefixes=("/api/",),
)

# Configure CORS: Wildcard origin "*" NEVER allowed with credentials per W3C specification
cors_allow_credentials = False if ("*" in settings.ALLOWED_ORIGINS) else True
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


from tripmate.core.errors import AppException


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    request_id = getattr(request.state, "request_id", f"req_{uuid.uuid4().hex[:12]}")
    return JSONResponse(
        status_code=exc.status_code,
        content=APIResponse(
            success=False,
            data=None,
            error=ErrorDetail(code=exc.code.value, message=exc.message, details=exc.details),
            request_id=request_id,
        ).model_dump(),
    )


@app.exception_handler(FastAPIHTTPException)
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    request_id = getattr(request.state, "request_id", f"req_{uuid.uuid4().hex[:12]}")
    code = "HTTP_ERROR"
    message = str(exc.detail)
    details = None

    if isinstance(exc.detail, dict):
        code = exc.detail.get("code", "HTTP_ERROR")
        message = exc.detail.get("message", str(exc.detail))
        details = exc.detail.get("details", None)

    return JSONResponse(
        status_code=exc.status_code,
        content=APIResponse(
            success=False,
            data=None,
            error=ErrorDetail(code=code, message=message, details=details),
            request_id=request_id,
        ).model_dump(),
        headers=getattr(exc, "headers", None) or {},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    request_id = getattr(request.state, "request_id", f"req_{uuid.uuid4().hex[:12]}")
    raw_errors = exc.errors()
    first_err = raw_errors[0]["msg"] if raw_errors else "Invalid request body parameters."
    serialized_errors = jsonable_encoder(raw_errors)
    return JSONResponse(
        status_code=422,
        content=APIResponse(
            success=False,
            data=None,
            error=ErrorDetail(
                code="VALIDATION_ERROR",
                message=first_err,
                details=serialized_errors,
            ),
            request_id=request_id,
        ).model_dump(),
    )


@app.exception_handler(Exception)
async def global_unhandled_exception_handler(request: Request, exc: Exception):
    # Catch-all exception handler: log full traceback internally and return sanitized response
    request_id = getattr(request.state, "request_id", f"req_{uuid.uuid4().hex[:12]}")
    logger.error(
        f"Unhandled exception on {request.method} {request.url.path} (request_id={request_id}): {exc}",
        exc_info=True,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=APIResponse(
            success=False,
            data=None,
            error=ErrorDetail(
                code="INTERNAL_SERVER_ERROR",
                message="An unexpected internal error occurred. Please try again later.",
            ),
            request_id=request_id,
        ).model_dump(),
    )




# =========================================================
# Mount Versioned API Routes (/api/v1) & Global Endpoints
# =========================================================

# Expose /metrics at root level for Prometheus standard scrapers
app.include_router(metrics_v1_router)

v1_router = APIRouter(prefix="/api/v1")

# 1. Health & Diagnostics
v1_router.include_router(health_v1_router)

# 2. System Status
v1_router.include_router(status_v1_router)

# 3. AI Analysis
v1_router.include_router(ai_analysis_v1_router)

# 4. Authentication & RBAC
v1_router.include_router(auth_v1_router)

# 5. Watchlists
v1_router.include_router(watchlists_v1_router)

# 6. Alerts & Notifications
v1_router.include_router(alerts_v1_router)

# 7. Assets & Documents
v1_router.include_router(assets_v1_router)

# 8. Financial Engine
v1_router.include_router(financial_v1_router)

# 9. Administration
v1_router.include_router(admin_v1_router)

# 10. AI Orchestration, Agents, Travel & HITL Approval
v1_router.include_router(ai_v1_router)
v1_router.include_router(travel_v1_router)
v1_router.include_router(approval_v1_router)
v1_router.include_router(runs_v1_router)

# 11. Monitoring Metrics (/api/v1/metrics)
v1_router.include_router(metrics_v1_router)

# 12. Background Task Queue (/api/v1/tasks)
v1_router.include_router(tasks_v1_router)

# 13. GDS Travel Booking & Search (/api/v1/booking)
v1_router.include_router(booking_v1_router)

app.include_router(v1_router)


# Legacy request payload schemas
class LegacyTravelRequest(BaseModel):
    model_config = {"extra": "forbid"}

    message: str = Field(..., min_length=1, max_length=2000)
    thread_id: Optional[str] = Field(default=None, max_length=128)

    @field_validator("message")
    @classmethod
    def clean_message(cls, v: str) -> str:
        return strip_control_chars(v)

    @field_validator("thread_id")
    @classmethod
    def clean_thread_id(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = strip_control_chars(v).strip()
        if not cleaned:
            return None
        if not re.match(settings.THREAD_ID_REGEX, cleaned):
            raise ValueError(f"Invalid thread_id format. Must match regex '{settings.THREAD_ID_REGEX}'.")
        return cleaned


class LegacyApprovalRequest(BaseModel):
    model_config = {"extra": "forbid"}

    thread_id: str = Field(..., min_length=1, max_length=128)
    approved: bool
    feedback: str = Field(default="", max_length=1000)

    @field_validator("thread_id")
    @classmethod
    def clean_thread_id(cls, v: str) -> str:
        cleaned = strip_control_chars(v).strip()
        if not re.match(settings.THREAD_ID_REGEX, cleaned):
            raise ValueError(f"Invalid thread_id format. Must match regex '{settings.THREAD_ID_REGEX}'.")
        return cleaned

    @field_validator("feedback")
    @classmethod
    def clean_feedback(cls, v: str) -> str:
        return strip_control_chars(v).strip()


# Production Root Metadata & Navigation Endpoint
@app.get(
    "/",
    summary="API Information",
    description="Returns basic information, operational status, and available entry points for the Multi-Agent AI API.",
    response_model=APIRootResponse,
)
async def root():
    """Production root endpoint returning top-level API metadata and entry points."""
    return APIRootResponse(
        name=settings.APP_NAME,
        description="Production-grade Multi-Agent AI Orchestration Platform",
        version=settings.APP_VERSION,
        status="operational",
        environment=settings.APP_ENV,
        api_base="/api/v1",
        docs="/docs" if (not settings.is_production or settings.ENABLE_DOCS_IN_PROD) else "",
        health="/api/v1/health",
        status_endpoint="/api/v1/status",
    )


# Backward-compatibility endpoint aliases protected with get_current_user dependency
@app.post("/api/travel")
async def legacy_travel(
    request_data: LegacyTravelRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Legacy endpoint alias for POST /api/v1/travel with strict authentication and thread binding."""
    user_message = request_data.message.strip()
    if not user_message:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "Message cannot be empty."},
        )
    server_thread_id = request_data.thread_id or f"thread_{uuid.uuid4().hex}"
    result = await travel_service.execute_travel_plan(
        user_message,
        server_thread_id,
        user_id=current_user.get("id"),
    )
    return JSONResponse(content={"success": True, **result})


@app.post("/api/travel/stream")
async def legacy_travel_stream(
    request_data: LegacyTravelRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Legacy endpoint alias for POST /api/v1/travel/stream with strict authentication."""
    user_message = request_data.message.strip()
    request_id = getattr(request.state, "request_id", f"req_{uuid.uuid4().hex[:12]}")
    if not user_message:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "Message cannot be empty."},
        )
    server_thread_id = request_data.thread_id or f"thread_{uuid.uuid4().hex}"
    generator = travel_service.stream_travel_events(
        user_message,
        server_thread_id,
        request_id,
        user_id=current_user.get("id"),
        request=request,
    )
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.post("/api/travel/approve")
async def legacy_approve(
    request_data: LegacyApprovalRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Legacy endpoint alias for POST /api/v1/travel/approve with strict authentication and authorization."""
    if not request_data.approved and not request_data.feedback.strip():
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "Please provide revision feedback when rejecting the draft."},
        )
    result = await travel_service.resume_travel_plan(
        thread_id=request_data.thread_id,
        approved=request_data.approved,
        feedback=request_data.feedback,
        user_id=current_user.get("id"),
    )
    return JSONResponse(content={"success": True, **result})


from fastapi import Response
from tripmate.database import check_db_health


@app.get("/health/live", tags=["System Health & Diagnostics"])
async def health_live():
    """Process Liveness Probe: Verifies web server is running and alive with no internal leaks."""
    return {"status": "ok"}


@app.get("/health/ready", tags=["System Health & Diagnostics"])
async def health_ready(response: Response):
    """Readiness Probe: Verifies PostgreSQL, Redis, and MCP connectivity without leaking secrets."""
    db_health = check_db_health()
    db_ok = db_health.get("status") in ("healthy", "disabled") if settings.is_dev else (db_health.get("status") == "healthy")

    redis_ok = True
    try:
        redis_ping = await hybrid_cache.ping()
        if not redis_ping:
            redis_ok = False
    except Exception:
        redis_ok = False

    # MCP service availability
    mcp_ok = True
    try:
        from mcp_client import mcp_manager
        if hasattr(mcp_manager, "is_healthy") and not mcp_manager.is_healthy():
            mcp_ok = False
    except Exception:
        mcp_ok = True

    is_ready = db_ok and redis_ok and mcp_ok
    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "unhealthy",
            "services": {
                "database": "healthy" if db_ok else "unhealthy",
                "redis": "healthy" if redis_ok else "unhealthy",
                "mcp": "healthy" if mcp_ok else "unhealthy",
            },
        }

    return {
        "status": "ready",
        "services": {
            "database": "healthy",
            "redis": "healthy",
            "mcp": "healthy",
        },
    }


@app.get("/health")
async def legacy_health():
    """Minimal public health check."""
    res = {
        "status": "ok",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }
    if not settings.is_production:
        res["features"] = [
            "supervisor_agent",
            "parallel_supervisor_agent",
            "pydantic_output_guardrail",
            "human_in_the_loop",
            "async_sse_streaming",
            "sliding_window_rate_limiter",
        ]
    return res


if __name__ == "__main__":
    raw_port = os.getenv("PORT", str(settings.PORT)).strip()
    try:
        port = int(raw_port)
    except ValueError:
        port = settings.PORT

    trusted = settings.TRUSTED_PROXIES
    allowed_proxies = ",".join(trusted) if isinstance(trusted, list) else str(trusted)

    if settings.is_dev:
        # Development mode: localhost only, reload=True
        uvicorn.run(
            "app:app",
            host="127.0.0.1",
            port=port,
            reload=True,
            proxy_headers=True,
            forwarded_allow_ips=allowed_proxies,
        )
    else:
        # Production mode: gunicorn + uvicorn workers, proxy headers, graceful timeout, keep-alive
        import sys
        workers = int(os.getenv("WEB_CONCURRENCY", os.getenv("WORKERS", str(settings.WEB_CONCURRENCY))))
        graceful_timeout = int(os.getenv("GRACEFUL_TIMEOUT", str(settings.GRACEFUL_TIMEOUT)))
        keep_alive = int(os.getenv("KEEP_ALIVE", str(settings.KEEP_ALIVE)))

        if sys.platform != "win32":
            import subprocess
            cmd = [
                "gunicorn",
                "-c", "gunicorn.conf.py",
                "app:app",
            ]
            subprocess.run(cmd)
        else:
            uvicorn.run(
                "app:app",
                host="0.0.0.0",
                port=port,
                workers=workers,
                reload=False,
                proxy_headers=True,
                forwarded_allow_ips=allowed_proxies,
                timeout_keep_alive=keep_alive,
                timeout_graceful_shutdown=graceful_timeout,
            )
