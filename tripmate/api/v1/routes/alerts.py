"""
Alerts & Notifications API Router

Endpoints:
- GET /api/v1/alerts: List active alerts for user
- POST /api/v1/alerts: Create a custom price/event alert
- PUT /api/v1/alerts/{alert_id}/read: Mark alert as read
- DELETE /api/v1/alerts/{alert_id}: Delete alert notification
"""

from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException, Request, status
from tripmate.schemas import APIResponse, AlertCreateRequest, AlertItem
from tripmate.services.alert_service import alert_service
from tripmate.api.dependencies import get_current_user

router = APIRouter(prefix="/alerts", tags=["Alerts & Notifications"])


@router.get(
    "",
    summary="List User Alerts",
    description="Returns all alert notifications for the authenticated user.",
    response_model=APIResponse[List[AlertItem]],
)
async def list_alerts(request: Request, current_user: Dict[str, Any] = Depends(get_current_user)):
    request_id = getattr(request.state, "request_id", "req_alt")
    alerts = alert_service.list_alerts(current_user["id"])
    return APIResponse(
        success=True,
        data=alerts,
        error=None,
        request_id=request_id,
    )


@router.post(
    "",
    summary="Create New Alert",
    description="Creates a new price drop, weather warning, or schedule alert.",
    response_model=APIResponse[AlertItem],
)
async def create_alert(
    req: AlertCreateRequest,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    request_id = getattr(request.state, "request_id", "req_alt")
    alert = alert_service.create_alert(current_user["id"], req)
    return APIResponse(
        success=True,
        data=alert,
        error=None,
        request_id=request_id,
    )


@router.put(
    "/{alert_id}/read",
    summary="Mark Alert as Read",
    description="Marks an alert notification as acknowledged/read.",
    response_model=APIResponse[AlertItem],
)
async def mark_read(
    alert_id: str,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    request_id = getattr(request.state, "request_id", "req_alt")
    alert = alert_service.mark_as_read(alert_id, current_user["id"])
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "ALERT_NOT_FOUND", "message": f"Alert ID '{alert_id}' not found."},
        )
    return APIResponse(
        success=True,
        data=alert,
        error=None,
        request_id=request_id,
    )


@router.delete(
    "/{alert_id}",
    summary="Delete Alert",
    description="Deletes an alert notification permanently.",
    response_model=APIResponse[Dict[str, Any]],
)
async def delete_alert(
    alert_id: str,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    request_id = getattr(request.state, "request_id", "req_alt")
    deleted = alert_service.delete_alert(alert_id, current_user["id"])
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "ALERT_NOT_FOUND", "message": f"Alert ID '{alert_id}' not found."},
        )
    return APIResponse(
        success=True,
        data={"deleted": True, "id": alert_id},
        error=None,
        request_id=request_id,
    )
