"""
Background Tasks API Router

Endpoints:
- POST /api/v1/tasks/submit: Enqueue a background task
- GET /api/v1/tasks/{task_id}: Get status and results of a task
- GET /api/v1/tasks: List background tasks
- POST /api/v1/tasks/{task_id}/cancel: Cancel a running or pending task
"""

import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from tripmate.api.dependencies import get_current_user
from tripmate.schemas import APIResponse
from tripmate.tasks.queue import task_queue
import tripmate.tasks.workers  # Ensure default worker handlers are loaded

router = APIRouter(prefix="/tasks", tags=["Background Tasks & Queue"])


class TaskSubmitRequest(BaseModel):
    task_name: str = Field(..., description="Name of registered background task (e.g. watchlist_price_scan, background_itinerary, system_health_audit)")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Task argument parameters")


@router.post("/submit", response_model=APIResponse[Dict[str, Any]], summary="Submit a background task")
async def submit_task(
    req: TaskSubmitRequest,
    request: Request,
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user),
):
    request_id = getattr(request.state, "request_id", f"req_{uuid.uuid4().hex[:12]}")
    user_id = current_user.get("id") or current_user.get("uid") if current_user else None
    user_role = current_user.get("role") or current_user.get("rol") if current_user else "user"

    payload = dict(req.payload)
    if user_id and "user_id" not in payload:
        payload["user_id"] = user_id
    if user_role and "user_role" not in payload:
        payload["user_role"] = user_role

    try:
        task_record = await task_queue.submit_task(
            task_name=req.task_name,
            payload=payload,
            user_id=user_id,
        )
        return APIResponse(
            success=True,
            data=task_record,
            error=None,
            request_id=request_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_TASK_TYPE", "message": str(exc)},
        )


@router.get("/{task_id}", response_model=APIResponse[Dict[str, Any]], summary="Get task execution status")
async def get_task_status(
    task_id: str,
    request: Request,
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user),
):
    request_id = getattr(request.state, "request_id", f"req_{uuid.uuid4().hex[:12]}")
    user_id = current_user.get("id") or current_user.get("uid") if current_user else None
    user_role = current_user.get("role") or current_user.get("rol") if current_user else "user"

    effective_user_id = None if user_role == "admin" else user_id
    task = task_queue.get_task(task_id, user_id=effective_user_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "TASK_NOT_FOUND", "message": f"Task '{task_id}' not found or access denied."},
        )
    return APIResponse(
        success=True,
        data=task,
        error=None,
        request_id=request_id,
    )


@router.get("", response_model=APIResponse[List[Dict[str, Any]]], summary="List background tasks")
async def list_tasks(
    request: Request,
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status"),
    limit: int = Query(50, ge=1, le=100),
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user),
):
    request_id = getattr(request.state, "request_id", f"req_{uuid.uuid4().hex[:12]}")
    user_id = current_user.get("id") or current_user.get("uid") if current_user else None
    user_role = current_user.get("role") or current_user.get("rol") if current_user else "user"

    effective_user_id = None if user_role == "admin" else user_id
    tasks = task_queue.list_tasks(
        user_id=effective_user_id,
        status=status_filter,
        limit=limit,
    )
    return APIResponse(
        success=True,
        data=tasks,
        error=None,
        request_id=request_id,
    )


@router.post("/{task_id}/cancel", response_model=APIResponse[Dict[str, Any]], summary="Cancel a task")
async def cancel_task(
    task_id: str,
    request: Request,
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user),
):
    request_id = getattr(request.state, "request_id", f"req_{uuid.uuid4().hex[:12]}")
    user_id = current_user.get("id") or current_user.get("uid") if current_user else None
    user_role = current_user.get("role") or current_user.get("rol") if current_user else "user"

    effective_user_id = None if user_role == "admin" else user_id
    cancelled = await task_queue.cancel_task(task_id, user_id=effective_user_id)
    if not cancelled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "CANCEL_FAILED", "message": f"Could not cancel task '{task_id}'. It may already be completed or does not exist."},
        )
    return APIResponse(
        success=True,
        data={"task_id": task_id, "status": "CANCELLED"},
        error=None,
        request_id=request_id,
    )
