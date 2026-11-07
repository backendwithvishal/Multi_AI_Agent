import uuid
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from tripmate.api.dependencies import get_current_user
from tripmate.config.settings import settings
from tripmate.schemas import APIResponse, ErrorDetail, TravelRequest
from tripmate.services.observability import estimate_tokens, token_budget_tracker
from tripmate.services.travel_service import travel_service

router = APIRouter(prefix="/travel", tags=["Travel Multi-Agent API"])


@router.post(
    "",
    summary="Execute Travel Multi-Agent Workflow",
    description="Runs input guardrail, dynamic supervisor agent, parallel specialist nodes, and synthesizes a travel plan.",
    response_model=APIResponse,
)
async def create_travel_plan(
    request_data: TravelRequest,
    request: Request,
    response: Response = None,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    request_id = getattr(request.state, "request_id", f"req_{uuid.uuid4().hex[:12]}")
    effective_user_id = current_user.get("id") or "anonymous"

    # Enforce daily token budget
    remaining = token_budget_tracker.get_remaining(effective_user_id, settings.DAILY_TOKEN_BUDGET_PER_USER)
    if remaining <= 0:
        return JSONResponse(
            status_code=429,
            content=APIResponse(
                success=False,
                data=None,
                error=ErrorDetail(
                    code="DAILY_TOKEN_BUDGET_EXCEEDED",
                    message="Daily token budget exceeded for this user account.",
                ),
                request_id=request_id,
            ).model_dump(),
            headers={"X-TokenBudget-Remaining": "0"},
        )

    # Set initial header on response if response object is present
    if response is not None:
        response.headers["X-TokenBudget-Remaining"] = str(remaining)

    if request_data.thread_id:
        import asyncio

        from tripmate.database.store import store

        existing_owner = await asyncio.to_thread(store.get_thread_owner, request_data.thread_id)
        if existing_owner and existing_owner != effective_user_id:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "THREAD_NOT_FOUND",
                    "message": f"Thread '{request_data.thread_id}' not found or access is not authorized.",
                },
            )
    server_thread_id = request_data.thread_id or f"thread_{uuid.uuid4().hex}"

    try:
        result = await travel_service.execute_travel_plan(
            user_input=request_data.message,
            thread_id=server_thread_id,
            user_id=effective_user_id,
        )
        est_tokens = estimate_tokens(request_data.message) + estimate_tokens(str(result))
        remaining = token_budget_tracker.consume(effective_user_id, est_tokens, settings.DAILY_TOKEN_BUDGET_PER_USER)
        if response is not None:
            response.headers["X-TokenBudget-Remaining"] = str(remaining)

        return APIResponse(
            success=True,
            data=result,
            error=None,
            request_id=request_id,
        )
    except HTTPException:
        raise
    except Exception:
        return JSONResponse(
            status_code=500,
            content=APIResponse(
                success=False,
                data=None,
                error=ErrorDetail(
                    code="TRAVEL_WORKFLOW_ERROR",
                    message="An unexpected error occurred during travel plan execution.",
                ),
                request_id=request_id,
            ).model_dump(),
            headers={"X-TokenBudget-Remaining": str(remaining)},
        )


@router.post(
    "/stream",
    summary="Stream Travel Execution Events (SSE)",
    description="Streams real-time agent execution state events using Server-Sent Events.",
)
async def stream_travel_plan(
    request_data: TravelRequest,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    request_id = getattr(request.state, "request_id", f"req_{uuid.uuid4().hex[:12]}")
    effective_user_id = current_user.get("id")
    if request_data.thread_id:
        import asyncio

        from tripmate.database.store import store

        existing_owner = await asyncio.to_thread(store.get_thread_owner, request_data.thread_id)
        if existing_owner and existing_owner != effective_user_id:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "THREAD_NOT_FOUND",
                    "message": f"Thread '{request_data.thread_id}' not found or access is not authorized.",
                },
            )
    server_thread_id = request_data.thread_id or f"thread_{uuid.uuid4().hex}"

    generator = travel_service.stream_travel_events(
        user_input=request_data.message,
        thread_id=server_thread_id,
        request_id=request_id,
        user_id=effective_user_id,
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
