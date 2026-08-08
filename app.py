import json
import traceback
import uuid

import uvicorn
from fastapi import FastAPI, Request, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from tripmate.config.settings import settings
from tripmate.middleware import (
    RequestIDMiddleware,
    SlidingWindowRateLimiter,
    SecurityHeadersMiddleware,
    StructuredLoggingMiddleware,
)

from tripmate.api.v1.routes.travel import router as travel_v1_router
from tripmate.api.v1.routes.approval import router as approval_v1_router
from tripmate.api.v1.routes.health import router as health_v1_router
from tripmate.services.travel_service import travel_service

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
)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(StructuredLoggingMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(
    SlidingWindowRateLimiter,
    max_requests=settings.RATE_LIMIT_REQUESTS,
    window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
    protected_prefixes=("/api/",),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(travel_v1_router)
v1_router.include_router(approval_v1_router)
v1_router.include_router(health_v1_router)
app.include_router(v1_router)


class TravelRequest(BaseModel):
    message: str
    thread_id: str | None = None


class ApprovalRequest(BaseModel):
    thread_id: str = Field(min_length=1)
    approved: bool
    feedback: str = ""


@app.get("/")
async def root(request: Request):
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs_url": "/docs",
        "request_id": getattr(request.state, "request_id", None),
        "endpoints": {
            "travel": "POST /api/v1/travel",
            "travel_stream": "POST /api/v1/travel/stream",
            "travel_approve": "POST /api/v1/travel/approve",
            "health": "GET /api/v1/health",
            "liveness": "GET /api/v1/liveness",
            "readiness": "GET /api/v1/readiness",
        },
        "v1_endpoints": {
            "travel": "POST /api/v1/travel",
            "travel_stream": "POST /api/v1/travel/stream",
            "travel_approve": "POST /api/v1/travel/approve",
            "health": "GET /api/v1/health",
            "liveness": "GET /api/v1/liveness",
            "readiness": "GET /api/v1/readiness",
        },
    }


@app.post("/api/travel")
async def legacy_travel(request_data: TravelRequest, request: Request):
    user_message = request_data.message.strip()
    if not user_message:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "Message cannot be empty."},
        )
    result = await travel_service.execute_travel_plan(user_message, request_data.thread_id)
    return JSONResponse(content={"success": True, **result})


@app.post("/api/travel/stream")
async def legacy_travel_stream(request_data: TravelRequest, request: Request):
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
async def legacy_approve(request_data: ApprovalRequest, request: Request):
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
    return {
        "status": "ok",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "features": [
            "supervisor_agent",
            "parallel_supervisor_agent",
            "pydantic_output_guardrail",
            "human_in_the_loop",
            "async_sse_streaming",
            "sliding_window_rate_limiter",
            "request_correlation_tracing",
            "ttl_mcp_caching",
            "circuit_breaker_resilience",
        ],
    }


if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
