"""
Travel Notifications & Price Alerts API Router

Endpoints:
- GET /api/v1/notifications: List active alerts/notifications for user
- POST /api/v1/notifications: Create a custom price/event notification
- PUT /api/v1/notifications/{alert_id}/read: Mark notification as read
- DELETE /api/v1/notifications/{alert_id}: Delete notification
"""

import asyncio
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request, status

from tripmate.api.dependencies import get_current_user
from tripmate.schemas import AlertCreateRequest, AlertItem, APIResponse
from tripmate.services.notification_service import notification_service

router = APIRouter(prefix="/notifications", tags=["Travel Notifications & Alerts"])
price_alerts_router = APIRouter(prefix="/price-alerts", tags=["Travel Notifications & Alerts (Price Alert Alias)"])
legacy_router = APIRouter(prefix="/alerts", tags=["Travel Notifications & Alerts (Legacy Alias)"])


async def _handle_list(request: Request, current_user: Dict[str, Any]) -> APIResponse[List[AlertItem]]:
    request_id = getattr(request.state, "request_id", "req_notif")
    alerts = await asyncio.to_thread(notification_service.list_alerts, current_user["id"])
    return APIResponse(success=True, data=alerts, error=None, request_id=request_id)


async def _handle_create(
    req: AlertCreateRequest, request: Request, current_user: Dict[str, Any]
) -> APIResponse[AlertItem]:
    request_id = getattr(request.state, "request_id", "req_notif")
    alert = await asyncio.to_thread(notification_service.create_alert, current_user["id"], req)
    return APIResponse(success=True, data=alert, error=None, request_id=request_id)


async def _handle_read(alert_id: str, request: Request, current_user: Dict[str, Any]) -> APIResponse[AlertItem]:
    request_id = getattr(request.state, "request_id", "req_notif")
    alert = await asyncio.to_thread(notification_service.mark_as_read, alert_id, current_user["id"])
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "ALERT_NOT_FOUND",
                "message": f"Alert ID '{alert_id}' not found.",
            },
        )
    return APIResponse(success=True, data=alert, error=None, request_id=request_id)


async def _handle_delete(alert_id: str, request: Request, current_user: Dict[str, Any]) -> APIResponse[Dict[str, Any]]:
    request_id = getattr(request.state, "request_id", "req_notif")
    deleted = await asyncio.to_thread(notification_service.delete_alert, alert_id, current_user["id"])
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "ALERT_NOT_FOUND",
                "message": f"Alert ID '{alert_id}' not found.",
            },
        )
    return APIResponse(
        success=True,
        data={"deleted": True, "id": alert_id},
        error=None,
        request_id=request_id,
    )


# Canonical /notifications
@router.get("", summary="List Notifications", response_model=APIResponse[List[AlertItem]])
async def list_notifications(request: Request, current_user: Dict[str, Any] = Depends(get_current_user)):
    return await _handle_list(request, current_user)


@router.post("", summary="Create Notification", response_model=APIResponse[AlertItem])
async def create_notification(
    req: AlertCreateRequest,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    return await _handle_create(req, request, current_user)


@router.put(
    "/{alert_id}/read",
    summary="Mark Notification as Read",
    response_model=APIResponse[AlertItem],
)
async def mark_notification_read(
    alert_id: str,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    return await _handle_read(alert_id, request, current_user)


@router.delete(
    "/{alert_id}",
    summary="Delete Notification",
    response_model=APIResponse[Dict[str, Any]],
)
async def delete_notification(
    alert_id: str,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    return await _handle_delete(alert_id, request, current_user)


# /price-alerts
@price_alerts_router.get("", summary="List Price Alerts", response_model=APIResponse[List[AlertItem]])
async def list_price_alerts(request: Request, current_user: Dict[str, Any] = Depends(get_current_user)):
    return await _handle_list(request, current_user)


@price_alerts_router.post("", summary="Create Price Alert", response_model=APIResponse[AlertItem])
async def create_price_alert(
    req: AlertCreateRequest,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    return await _handle_create(req, request, current_user)


@price_alerts_router.put(
    "/{alert_id}/read",
    summary="Mark Price Alert as Read",
    response_model=APIResponse[AlertItem],
)
async def mark_price_alert_read(
    alert_id: str,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    return await _handle_read(alert_id, request, current_user)


@price_alerts_router.delete(
    "/{alert_id}",
    summary="Delete Price Alert",
    response_model=APIResponse[Dict[str, Any]],
)
async def delete_price_alert(
    alert_id: str,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    return await _handle_delete(alert_id, request, current_user)


# Legacy /alerts
@legacy_router.get("", summary="Legacy List Alerts", response_model=APIResponse[List[AlertItem]])
async def list_alerts(request: Request, current_user: Dict[str, Any] = Depends(get_current_user)):
    return await _handle_list(request, current_user)


@legacy_router.post("", summary="Legacy Create Alert", response_model=APIResponse[AlertItem])
async def create_alert(
    req: AlertCreateRequest,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    return await _handle_create(req, request, current_user)


@legacy_router.put(
    "/{alert_id}/read",
    summary="Legacy Mark Alert as Read",
    response_model=APIResponse[AlertItem],
)
async def mark_read(
    alert_id: str,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    return await _handle_read(alert_id, request, current_user)


@legacy_router.delete(
    "/{alert_id}",
    summary="Legacy Delete Alert",
    response_model=APIResponse[Dict[str, Any]],
)
async def delete_alert(
    alert_id: str,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    return await _handle_delete(alert_id, request, current_user)
