import os
import uuid
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, APIRouter, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError, HTTPException as FastAPIHTTPException
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse, HTMLResponse
from pydantic import BaseModel, Field



from tripmate.config.settings import settings
from tripmate.middleware import (
    RequestIDMiddleware,
    SlidingWindowRateLimiter,
    SecurityHeadersMiddleware,
    StructuredLoggingMiddleware,
)
from tripmate.schemas import APIResponse, ErrorDetail

# Import all 10 API Domain Routers
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
from tripmate.services.travel_service import travel_service


import logging
from tripmate.cache.redis_cache import hybrid_cache

logger = logging.getLogger("tripmate.app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Perform production configuration check on application startup
    try:
        settings.validate_production()
    except ValueError as exc:
        if settings.APP_ENV == "production":
            logger.error(f"[STARTUP ERROR] {exc}")
            raise
        else:
            logger.warning(f"[STARTUP WARNING] {exc}")
    yield
    # Graceful shutdown hooks
    try:
        await hybrid_cache.aclose()
    except Exception as exc:
        logger.warning(f"[SHUTDOWN WARNING] Cache close: {exc}")


# Initialize FastAPI web app
app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "Production Enterprise Multi-Agent Travel Planner Engine built with "
        "LangGraph, MCP, FastAPI, Async SSE Streaming, Sliding Window Rate Limiting, "
        "Circuit Breakers, and Human-in-the-Loop approval workflows."
    ),
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Register HTTP middleware chain in order of execution
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(StructuredLoggingMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(
    SlidingWindowRateLimiter,
    max_requests=settings.RATE_LIMIT_REQUESTS,
    window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
    protected_prefixes=("/api/",),
)

# Configure CORS: If wildcard origin is used, allow_credentials is set to False per W3C spec
cors_allow_credentials = False if settings.ALLOWED_ORIGINS == ["*"] else True
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================================
# Centralized Exception Handlers (Standardized APIResponse)
# =========================================================

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
# Mount Versioned API Routes (/api/v1)
# =========================================================

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

app.include_router(v1_router)


# Legacy request payload schemas
class LegacyTravelRequest(BaseModel):
    message: str
    thread_id: str | None = None


class LegacyApprovalRequest(BaseModel):
    thread_id: str = Field(min_length=1)
    approved: bool
    feedback: str = ""


# Root health & landing endpoint
@app.get("/")
async def root(request: Request):
    """Production root landing dashboard & metadata probe."""
    request_id = getattr(request.state, "request_id", f"req_{uuid.uuid4().hex[:12]}")
    accept_header = request.headers.get("accept", "")

    # Return polished HTML Dashboard for browser visits
    if "text/html" in accept_header and "application/json" not in accept_header:
        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{settings.APP_NAME}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: radial-gradient(circle at 50% 0%, #1a1f35 0%, #0a0d18 100%);
            color: #f1f5f9;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 24px;
        }}
        .card {{
            background: rgba(15, 23, 42, 0.75);
            backdrop-filter: blur(16px);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 20px;
            max-width: 680px;
            width: 100%;
            padding: 40px;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5), 0 0 40px rgba(56, 189, 248, 0.1);
        }}
        .header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 24px;
        }}
        .badge {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 6px 14px;
            border-radius: 9999px;
            font-size: 13px;
            font-weight: 600;
            background: rgba(34, 197, 94, 0.15);
            color: #4ade80;
            border: 1px solid rgba(34, 197, 94, 0.3);
        }}
        .dot {{
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: #22c55e;
            box-shadow: 0 0 10px #22c55e;
            animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
        }}
        @keyframes pulse {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: .5; }} }}
        h1 {{
            font-size: 28px;
            font-weight: 800;
            letter-spacing: -0.5px;
            background: linear-gradient(135deg, #ffffff 0%, #94a3b8 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 12px;
        }}
        p.subtitle {{
            color: #94a3b8;
            font-size: 15px;
            line-height: 1.6;
            margin-bottom: 32px;
        }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 16px;
            margin-bottom: 32px;
        }}
        .stat-box {{
            background: rgba(30, 41, 59, 0.5);
            border: 1px solid rgba(255, 255, 255, 0.05);
            border-radius: 12px;
            padding: 16px;
        }}
        .stat-label {{ font-size: 12px; color: #64748b; font-weight: 500; text-transform: uppercase; letter-spacing: 0.5px; }}
        .stat-val {{ font-size: 16px; font-weight: 600; color: #e2e8f0; margin-top: 4px; }}
        .actions {{
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
        }}
        .btn {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 12px 20px;
            border-radius: 10px;
            font-size: 14px;
            font-weight: 600;
            text-decoration: none;
            transition: all 0.2s ease;
        }}
        .btn-primary {{
            background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
            color: #ffffff;
            box-shadow: 0 4px 14px rgba(37, 99, 235, 0.4);
        }}
        .btn-primary:hover {{
            background: linear-gradient(135deg, #60a5fa 0%, #3b82f6 100%);
            transform: translateY(-1px);
        }}
        .btn-secondary {{
            background: rgba(51, 65, 85, 0.6);
            color: #e2e8f0;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }}
        .btn-secondary:hover {{
            background: rgba(71, 85, 105, 0.8);
            transform: translateY(-1px);
        }}
        .footer {{
            margin-top: 28px;
            font-size: 12px;
            color: #64748b;
            text-align: center;
        }}
    </style>
</head>
<body>
    <div class="card">
        <div class="header">
            <span class="badge"><span class="dot"></span> Systems Operational</span>
            <span style="font-size: 13px; color: #64748b;">v{settings.APP_VERSION}</span>
        </div>
        <h1>{settings.APP_NAME}</h1>
        <p class="subtitle">Enterprise multi-agent autonomous travel planning backend powered by LangGraph, MCP tools, and real-time streaming.</p>
        
        <div class="grid">
            <div class="stat-box">
                <div class="stat-label">Environment</div>
                <div class="stat-val">{settings.APP_ENV.title()}</div>
            </div>
            <div class="stat-box">
                <div class="stat-label">API Status</div>
                <div class="stat-val" style="color: #4ade80;">Active (v1)</div>
            </div>
            <div class="stat-box">
                <div class="stat-label">Request ID</div>
                <div class="stat-val" style="font-family: monospace; font-size: 13px;">{request_id[:12]}...</div>
            </div>
        </div>

        <div class="actions">
            <a href="/docs" class="btn btn-primary" id="btn-docs">Explore Swagger Docs →</a>
            <a href="/redoc" class="btn btn-secondary" id="btn-redoc">ReDoc Specs</a>
            <a href="/api/v1/health" class="btn btn-secondary" id="btn-health">Health Telemetry</a>
        </div>

        <div class="footer">
            TripMate Backend Engine • Designed for Production Resilience
        </div>
    </div>
</body>
</html>"""
        return HTMLResponse(content=html_content, status_code=200)

    # Return concise structured JSON for API clients
    return {
        "service": settings.APP_NAME,
        "status": "online",
        "version": settings.APP_VERSION,
        "environment": settings.APP_ENV,
        "docs_url": "/docs",
        "redoc_url": "/redoc",
        "request_id": request_id,
        "endpoints": {
            "docs": "/docs",
            "redoc": "/redoc",
            "health": "GET /api/v1/health",
            "status": "GET /api/v1/status",
            "travel": "POST /api/v1/travel",
            "travel_stream": "POST /api/v1/travel/stream",
            "travel_approve": "POST /api/v1/travel/approve",
            "runs": "GET /api/v1/runs/{run_id}",
            "auth": "POST /api/v1/auth/login",
        },
    }



# Backward-compatibility endpoint aliases
@app.post("/api/travel")
async def legacy_travel(request_data: LegacyTravelRequest, request: Request):
    """Legacy endpoint alias for POST /api/v1/travel."""
    user_message = request_data.message.strip()
    if not user_message:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "Message cannot be empty."},
        )
    result = await travel_service.execute_travel_plan(user_message, request_data.thread_id)
    return JSONResponse(content={"success": True, **result})


@app.post("/api/travel/stream")
async def legacy_travel_stream(request_data: LegacyTravelRequest, request: Request):
    """Legacy endpoint alias for POST /api/v1/travel/stream."""
    user_message = request_data.message.strip()
    request_id = getattr(request.state, "request_id", f"req_{uuid.uuid4().hex[:12]}")
    if not user_message:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "Message cannot be empty."},
        )
    thread_id = request_data.thread_id or f"user_{uuid.uuid4().hex}"
    generator = travel_service.stream_travel_events(user_message, thread_id, request_id)
    return StreamingResponse(generator, media_type="text/event-stream")


@app.post("/api/travel/approve")
async def legacy_approve(request_data: LegacyApprovalRequest, request: Request):
    """Legacy endpoint alias for POST /api/v1/travel/approve."""
    if not request_data.approved and not request_data.feedback.strip():
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "Please provide revision feedback when rejecting the draft."},
        )
    result = await travel_service.resume_travel_plan(
        thread_id=request_data.thread_id,
        approved=request_data.approved,
        feedback=request_data.feedback,
    )
    return JSONResponse(content={"success": True, **result})


@app.get("/health")
async def legacy_health(request: Request):
    """Legacy endpoint alias for GET /api/v1/health."""
    return {
        "status": "ok",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "features": [
            "health",
            "status",
            "ai_analysis",
            "auth",
            "watchlists",
            "alerts",
            "assets",
            "financial",
            "admin",
            "ai",
            "supervisor_agent",
            "parallel_supervisor_agent",
            "pydantic_output_guardrail",
            "human_in_the_loop",
            "async_sse_streaming",
            "sliding_window_rate_limiter",
            "request_correlation_tracing",
            "ttl_mcp_caching",
            "circuit_breaker_resilience",
            "observability_runs_api",
        ],
    }



if __name__ == "__main__":
    raw_port = os.getenv("PORT", "8000").strip()
    try:
        port = int(raw_port)
    except ValueError:
        port = 8000
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)
