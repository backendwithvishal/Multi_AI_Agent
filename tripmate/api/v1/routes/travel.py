import uuid
from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from tripmate.schemas import TravelRequest, APIResponse, ErrorDetail
from tripmate.services.travel_service import travel_service
from tripmate.api.dependencies import get_current_user

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
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    request_id = getattr(request.state, "request_id", f"req_{uuid.uuid4().hex[:12]}")
    effective_user_id = request_data.user_id or current_user.get("id")
    try:
        result = await travel_service.execute_travel_plan(
            user_input=request_data.message,
            thread_id=request_data.thread_id,
            user_id=effective_user_id,
        )
        return APIResponse(
            success=True,
            data=result,
            error=None,
            request_id=request_id,
        )
    except HTTPException:
        raise
    except Exception as exc:
        err_msg = str(exc).strip() or "An unexpected error occurred during travel plan execution."
        return JSONResponse(
            status_code=500,
            content=APIResponse(
                success=False,
                data=None,
                error=ErrorDetail(
                    code="TRAVEL_WORKFLOW_ERROR",
                    message=err_msg,
                ),
                request_id=request_id,
            ).model_dump(),
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
    thread_id = request_data.thread_id or f"user_{uuid.uuid4().hex}"
    effective_user_id = request_data.user_id or current_user.get("id")

    generator = travel_service.stream_travel_events(
        user_input=request_data.message,
        thread_id=thread_id,
        request_id=request_id,
        user_id=effective_user_id,
    )
    return StreamingResponse(generator, media_type="text/event-stream")
