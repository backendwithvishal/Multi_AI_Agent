import uuid
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse

from tripmate.schemas import TravelRequest, APIResponse, ErrorDetail
from tripmate.services.travel_service import travel_service
from tripmate.api.dependencies import verify_api_key

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
    user_identity: str = Depends(verify_api_key),
):
    request_id = getattr(request.state, "request_id", f"req_{uuid.uuid4().hex[:12]}")
    try:
        result = await travel_service.execute_travel_plan(
            user_input=request_data.message,
            thread_id=request_data.thread_id,
            user_id=request_data.user_id,
        )
        return APIResponse(
            success=True,
            data=result,
            error=None,
            request_id=request_id,
        )
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content=APIResponse(
                success=False,
                data=None,
                error=ErrorDetail(
                    code="TRAVEL_WORKFLOW_ERROR",
                    message=f"An unexpected internal error occurred: {exc}",
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
    user_identity: str = Depends(verify_api_key),
):
    request_id = getattr(request.state, "request_id", f"req_{uuid.uuid4().hex[:12]}")
    thread_id = request_data.thread_id or f"user_{uuid.uuid4().hex}"

    generator = travel_service.stream_travel_events(
        user_input=request_data.message,
        thread_id=thread_id,
        request_id=request_id,
    )
    return StreamingResponse(generator, media_type="text/event-stream")
