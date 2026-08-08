import json
import traceback
import uuid
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from backend import resume_travel_agent, run_travel_agent
from backend_cache import mcp_cache
from middleware import RequestCorrelationMiddleware, SlidingWindowRateLimiterMiddleware

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(
    title="TripMate AI Backend",
    description=(
        "Production Enterprise Multi-Agent Travel Planner Engine built with "
        "LangGraph, MCP, FastAPI, Async Streaming, Sliding Window Rate Limiting, "
        "and Human-in-the-Loop approval workflows."
    ),
    version="2.5.0",
)

# 1. Attach Request Correlation ID Middleware
app.add_middleware(RequestCorrelationMiddleware)

# 2. Attach Sliding Window Rate Limiter Middleware (30 req/min per IP)
app.add_middleware(
    SlidingWindowRateLimiterMiddleware,
    max_requests=30,
    window_seconds=60,
    protected_paths=("/api/travel",),
)

# 3. CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount(
    "/static",
    StaticFiles(directory=str(BASE_DIR / "static")),
    name="static",
)

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


class TravelRequest(BaseModel):
    message: str
    thread_id: str | None = None


class ApprovalRequest(BaseModel):
    thread_id: str = Field(min_length=1)
    approved: bool
    feedback: str = ""


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={},
    )


@app.post("/api/travel")
async def travel_planner(request_data: TravelRequest, request: Request):
    try:
        user_message = request_data.message.strip()

        if not user_message:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "Message cannot be empty.",
                    "request_id": getattr(request.state, "request_id", None),
                },
            )

        result = await run_travel_agent(
            user_input=user_message,
            thread_id=request_data.thread_id,
        )

        return JSONResponse(
            content={
                "success": True,
                "request_id": getattr(request.state, "request_id", None),
                **result,
            }
        )

    except Exception as exc:
        print("ERROR:", exc)
        traceback.print_exc()

        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": "An unexpected internal error occurred while processing your request.",
                "request_id": getattr(request.state, "request_id", None),
            },
        )


@app.post("/api/travel/stream")
async def travel_planner_stream(request_data: TravelRequest, request: Request):
    """
    Async Server-Sent Events (SSE) Streaming endpoint for multi-agent graph execution.
    Streams progress events and telemetry updates to client.
    """
    user_message = request_data.message.strip()
    request_id = getattr(request.state, "request_id", f"req_{uuid.uuid4().hex[:12]}")

    if not user_message:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "Message cannot be empty.",
                "request_id": request_id,
            },
        )

    async def sse_generator():
        thread_id = request_data.thread_id or f"user_{uuid.uuid4().hex}"
        
        # Event 1: Initialized
        yield f"event: init\ndata: {json.dumps({'thread_id': thread_id, 'request_id': request_id, 'status': 'started'})}\n\n"

        try:
            result = await run_travel_agent(
                user_input=user_message,
                thread_id=thread_id,
            )

            # Event 2: Agent Progress updates
            selected = result.get("selected_agents", [])
            yield f"event: supervisor_decision\ndata: {json.dumps({'selected_agents': selected, 'reasoning': result.get('supervisor_reasoning')})}\n\n"

            for agent in selected:
                yield f"event: agent_completed\ndata: {json.dumps({'agent': agent, 'status': 'completed'})}\n\n"

            if result.get("requires_approval"):
                yield f"event: hitl_required\ndata: {json.dumps({'approval_request': result.get('approval_request')})}\n\n"

            # Event 3: Final execution result payload
            yield f"event: result\ndata: {json.dumps({'success': True, 'request_id': request_id, **result})}\n\n"

        except Exception as exc:
            yield f"event: error\ndata: {json.dumps({'success': False, 'error': str(exc), 'request_id': request_id})}\n\n"

    return StreamingResponse(sse_generator(), media_type="text/event-stream")


@app.post("/api/travel/approve")
async def approve_travel_plan(request_data: ApprovalRequest, request: Request):
    try:
        if not request_data.approved and not request_data.feedback.strip():
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "Please provide revision feedback when rejecting the draft.",
                    "request_id": getattr(request.state, "request_id", None),
                },
            )

        result = await resume_travel_agent(
            thread_id=request_data.thread_id,
            approved=request_data.approved,
            feedback=request_data.feedback,
        )

        return JSONResponse(
            content={
                "success": True,
                "request_id": getattr(request.state, "request_id", None),
                **result,
            }
        )

    except Exception as exc:
        print("APPROVAL ERROR:", exc)
        traceback.print_exc()

        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": "An unexpected internal error occurred while resuming the travel plan.",
                "request_id": getattr(request.state, "request_id", None),
            },
        )


@app.get("/health")
async def health_check(request: Request):
    return {
        "status": "ok",
        "service": "TripMate AI Multi-Agent Backend Engine",
        "version": app.version,
        "request_id": getattr(request.state, "request_id", None),
        "features": [
            "supervisor_agent",
            "parallel_supervisor_agent",
            "pydantic_output_guardrail",
            "human_in_the_loop",
            "async_sse_streaming",
            "sliding_window_rate_limiter",
            "request_correlation_tracing",
            "ttl_mcp_caching",
        ],
        "cache_stats": mcp_cache.get_stats(),
    }


@app.get("/favicon.ico")
async def favicon():
    return JSONResponse(content={})


if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )
