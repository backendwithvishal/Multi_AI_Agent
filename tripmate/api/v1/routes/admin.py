"""
Platform Administration & Management API Router

Endpoints:
- GET /api/v1/admin/stats: Platform aggregate statistics and circuit breaker states
- GET /api/v1/admin/users: List registered platform users
- POST /api/v1/admin/circuit-breakers/{service_name}/reset: Manually reset open circuit breakers
- POST /api/v1/admin/cache/clear: Purge platform cache
- GET /api/v1/admin/runs: Audit workflow execution history
"""

from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException, Request, status
from tripmate.schemas import APIResponse, AdminStatsResponse, UserRegisterRequest
from tripmate.services.admin_service import admin_service
from tripmate.services.travel_service import RUN_STORE
from tripmate.api.dependencies import require_admin

router = APIRouter(prefix="/admin", tags=["Platform Administration"])


@router.get(
    "/stats",
    summary="Platform Operational Statistics",
    description="Returns high-level statistics across users, runs, watchlists, alerts, and circuit breakers.",
    response_model=APIResponse[AdminStatsResponse],
)
async def get_stats(request: Request, admin_user: Dict[str, Any] = Depends(require_admin)):
    request_id = getattr(request.state, "request_id", "req_adm")
    stats = admin_service.get_platform_stats()
    return APIResponse(
        success=True,
        data=AdminStatsResponse(**stats),
        error=None,
        request_id=request_id,
    )


@router.get(
    "/users",
    summary="List Registered Users",
    description="Returns a list of all registered platform user accounts.",
    response_model=APIResponse[List[Dict[str, Any]]],
)
async def list_users(request: Request, admin_user: Dict[str, Any] = Depends(require_admin)):
    request_id = getattr(request.state, "request_id", "req_adm")
    users = admin_service.list_all_users()
    return APIResponse(
        success=True,
        data=users,
        error=None,
        request_id=request_id,
    )


@router.post(
    "/users",
    summary="Admin Provision User / Admin Account",
    description="Allows authenticated administrators to register new user or administrator accounts.",
    response_model=APIResponse[Dict[str, Any]],
)
async def create_user(
    req: UserRegisterRequest,
    request: Request,
    admin_user: Dict[str, Any] = Depends(require_admin),
):
    request_id = getattr(request.state, "request_id", "req_adm")
    try:
        token_data = admin_service.create_user_account(
            username=req.username,
            email=req.email,
            password=req.password,
            role=req.role,
        )
        return APIResponse(
            success=True,
            data=token_data,
            error=None,
            request_id=request_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "USER_CREATION_FAILED", "message": str(exc)},
        )


@router.post(
    "/circuit-breakers/{service_name}/reset",
    summary="Reset Circuit Breaker",
    description="Manually resets an open circuit breaker for Tavily, AviationStack, OpenWeather, or all.",
    response_model=APIResponse[Dict[str, Any]],
)
async def reset_circuit_breaker(
    service_name: str,
    request: Request,
    admin_user: Dict[str, Any] = Depends(require_admin),
):
    request_id = getattr(request.state, "request_id", "req_adm")
    res = admin_service.reset_circuit_breaker(service_name)
    return APIResponse(
        success=True,
        data=res,
        error=None,
        request_id=request_id,
    )


@router.post(
    "/cache/clear",
    summary="Purge Platform Cache",
    description="Purges all in-memory and Redis cached values.",
    response_model=APIResponse[Dict[str, Any]],
)
async def clear_cache(request: Request, admin_user: Dict[str, Any] = Depends(require_admin)):
    request_id = getattr(request.state, "request_id", "req_adm")
    res = await admin_service.clear_cache()
    return APIResponse(
        success=True,
        data=res,
        error=None,
        request_id=request_id,
    )


@router.get(
    "/runs",
    summary="Audit Platform Workflow Runs",
    description="Returns all logged multi-agent workflow executions.",
    response_model=APIResponse[List[Dict[str, Any]]],
)
async def list_runs(request: Request, admin_user: Dict[str, Any] = Depends(require_admin)):
    request_id = getattr(request.state, "request_id", "req_adm")
    runs = list(RUN_STORE.values())
    return APIResponse(
        success=True,
        data=runs,
        error=None,
        request_id=request_id,
    )
