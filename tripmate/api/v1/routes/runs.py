"""
Workflow Run Observability & Replay API Router

Endpoints:
- GET /api/v1/runs/{run_id}: Full run state
- GET /api/v1/runs/{run_id}/metrics: Latency, token usage, and cost metrics
- GET /api/v1/runs/{run_id}/agents: Agent outputs and evidence items
- POST /api/v1/runs/{run_id}/replay: Re-executes workflow run for debugging
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from tripmate.schemas import APIResponse, ErrorDetail
from tripmate.services.travel_service import RUN_STORE, travel_service
from tripmate.services.observability import summarize_run_observability
from tripmate.api.dependencies import verify_api_key

router = APIRouter(prefix="/runs", tags=["Workflow Observability & Replay API"])


@router.get(
    "/{run_id}",
    summary="Get Workflow Run Details",
    description="Retrieves execution details, graph outputs, and telemetry for a workflow run.",
    response_model=APIResponse,
)
async def get_run_details(
    run_id: str,
    request: Request,
    user_identity: str = Depends(verify_api_key),
):
    request_id = getattr(request.state, "request_id", "unknown")
    run_data = RUN_STORE.get(run_id)
    if not run_data:
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RUN_NOT_FOUND", "message": f"Run ID '{run_id}' not found."},
        )
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
    user_identity: str = Depends(verify_api_key),
):
    request_id = getattr(request.state, "request_id", "unknown")
    run_data = RUN_STORE.get(run_id)
    if not run_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RUN_NOT_FOUND", "message": f"Run ID '{run_id}' not found."},
        )
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
    user_identity: str = Depends(verify_api_key),
):
    request_id = getattr(request.state, "request_id", "unknown")
    run_data = RUN_STORE.get(run_id)
    if not run_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RUN_NOT_FOUND", "message": f"Run ID '{run_id}' not found."},
        )
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
    user_identity: str = Depends(verify_api_key),
):
    request_id = getattr(request.state, "request_id", "unknown")
    run_data = RUN_STORE.get(run_id)
    if not run_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RUN_NOT_FOUND", "message": f"Run ID '{run_id}' not found."},
        )

    prompt = run_data.get("answer") or "Replay request"
    thread_id = f"replay_{run_id}"

    new_result = await travel_service.execute_travel_plan(prompt, thread_id=thread_id)
    return APIResponse(success=True, data=new_result, error=None, request_id=request_id)
