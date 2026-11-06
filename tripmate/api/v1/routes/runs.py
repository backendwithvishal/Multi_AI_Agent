"""
Workflow Run Observability & Replay API Router

Endpoints:
- GET /api/v1/runs/{run_id}: Full run state
- GET /api/v1/runs/{run_id}/metrics: Latency, token usage, and cost metrics
- GET /api/v1/runs/{run_id}/agents: Agent outputs and evidence items
- POST /api/v1/runs/{run_id}/replay: Re-executes workflow run for debugging
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status

from tripmate.api.dependencies import get_current_user
from tripmate.schemas import APIResponse
from tripmate.services.observability import summarize_run_observability
from tripmate.services.travel_service import RUN_STORE, travel_service

router = APIRouter(prefix="/runs", tags=["Workflow Observability & Replay API"])


def _check_run_access(run_data: Dict[str, Any], current_user: Dict[str, Any]) -> None:
    owner_id = run_data.get("user_id")
    if owner_id and owner_id != current_user.get("id") and current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "RUN_NOT_FOUND",
                "message": "Run not found or access not authorized.",
            },
        )


@router.get(
    "/{run_id}",
    summary="Get Workflow Run Details",
    description="Retrieves execution details, graph outputs, and telemetry for a workflow run.",
    response_model=APIResponse,
)
async def get_run_details(
    run_id: str,
    request: Request,
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user),
    user_identity: Optional[Any] = None,
):
    request_id = getattr(request.state, "request_id", "unknown")
    user = current_user or ({"id": user_identity} if isinstance(user_identity, str) else user_identity) or {}
    run_data = RUN_STORE.get(run_id)
    if not run_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "RUN_NOT_FOUND",
                "message": f"Run ID '{run_id}' not found.",
            },
        )
    _check_run_access(run_data, user)
    return APIResponse(success=True, data=run_data, error=None, request_id=request_id)


@router.get(
    "/{run_id}/metrics",
    summary="Get Run Observability Metrics",
    description="Returns latency breakdowns, estimated token usage, and cost calculation.",
    response_model=APIResponse,
)
async def get_run_metrics(
    run_id: str,
    request: Request,
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user),
    user_identity: Optional[Any] = None,
):
    request_id = getattr(request.state, "request_id", "unknown")
    user = current_user or ({"id": user_identity} if isinstance(user_identity, str) else user_identity) or {}
    run_data = RUN_STORE.get(run_id)
    if not run_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "RUN_NOT_FOUND",
                "message": f"Run ID '{run_id}' not found.",
            },
        )
    _check_run_access(run_data, user)
    summary = summarize_run_observability(run_data)
    return APIResponse(success=True, data=summary, error=None, request_id=request_id)


@router.get(
    "/{run_id}/agents",
    summary="Get Agent Output & Evidence Items",
    description="Retrieves detailed agent outputs, evidence classifications, and critic reports.",
    response_model=APIResponse,
)
async def get_run_agents(
    run_id: str,
    request: Request,
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user),
    user_identity: Optional[Any] = None,
):
    request_id = getattr(request.state, "request_id", "unknown")
    user = current_user or ({"id": user_identity} if isinstance(user_identity, str) else user_identity) or {}
    run_data = RUN_STORE.get(run_id)
    if not run_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "RUN_NOT_FOUND",
                "message": f"Run ID '{run_id}' not found.",
            },
        )
    _check_run_access(run_data, user)
    agent_info = {
        "selected_agents": run_data.get("selected_agents", []),
        "structured_outputs": run_data.get("structured_outputs", {}),
        "evidence_items": run_data.get("evidence_items", []),
        "critic_report": run_data.get("critic_report"),
    }
    return APIResponse(success=True, data=agent_info, error=None, request_id=request_id)


@router.post(
    "/{run_id}/replay",
    summary="Replay Workflow Execution",
    description="Re-runs a workflow from initial inputs to test determinism or debug failures.",
    response_model=APIResponse,
)
async def replay_run(
    run_id: str,
    request: Request,
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user),
    user_identity: Optional[Any] = None,
):
    request_id = getattr(request.state, "request_id", "unknown")
    user = current_user or ({"id": user_identity} if isinstance(user_identity, str) else user_identity) or {}
    run_data = RUN_STORE.get(run_id)
    if not run_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "RUN_NOT_FOUND",
                "message": f"Run ID '{run_id}' not found.",
            },
        )
    _check_run_access(run_data, user)

    prompt = run_data.get("answer") or "Replay request"
    thread_id = f"replay_{run_id}"

    new_result = await travel_service.execute_travel_plan(prompt, thread_id=thread_id, user_id=user.get("id"))
    return APIResponse(success=True, data=new_result, error=None, request_id=request_id)
