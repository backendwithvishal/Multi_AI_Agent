import uuid
from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from tripmate.schemas import ApprovalRequest, APIResponse, ErrorDetail
from tripmate.services.travel_service import travel_service
from tripmate.api.dependencies import get_current_user

router = APIRouter(prefix="/travel", tags=["Human-in-the-Loop Approval API"])


@router.post(
    "/approve",
    summary="Approve or Reject Draft Travel Plan",
    description="Resumes a paused LangGraph thread with human approval or revision feedback.",
    response_model=APIResponse,
)
async def approve_travel_plan(
    request_data: ApprovalRequest,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    request_id = getattr(request.state, "request_id", f"req_{uuid.uuid4().hex[:12]}")
    effective_user_id = request_data.user_id or current_user.get("id")

    if not request_data.approved and not request_data.feedback.strip():
        return JSONResponse(
            status_code=400,
            content=APIResponse(
                success=False,
                data=None,
                error=ErrorDetail(
                    code="VALIDATION_ERROR",
                    message="Please provide revision feedback when rejecting the draft itinerary.",
                ),
                request_id=request_id,
            ).model_dump(),
        )

    try:
        result = await travel_service.resume_travel_plan(
            thread_id=request_data.thread_id,
            approved=request_data.approved,
            feedback=request_data.feedback,
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
        err_msg = str(exc).strip() or "An unexpected internal error occurred during workflow approval."
        return JSONResponse(
            status_code=500,
            content=APIResponse(
                success=False,
                data=None,
                error=ErrorDetail(
                    code="APPROVAL_WORKFLOW_ERROR",
                    message=err_msg,
                ),
                request_id=request_id,
            ).model_dump(),
        )
