"""
Alert Notification Domain Service

Manages travel price alerts, weather alerts, flight schedule notifications, and read statuses.
"""

from typing import Any, Dict, List, Optional
from tripmate.database.store import store
from tripmate.schemas import AlertCreateRequest, AlertItem


class AlertService:
    """Service managing platform alert notifications."""

    def create_alert(self, user_id: str, req: AlertCreateRequest) -> AlertItem:
        alert_data = store.create_alert(
            user_id=user_id,
            title=req.title,
            message=req.message,
            alert_type=req.alert_type,
            severity=req.severity,
            watchlist_id=req.watchlist_id,
        )
        return AlertItem(**alert_data)

    def list_alerts(self, user_id: str) -> List[AlertItem]:
        alerts = store.list_alerts(user_id)
        return [AlertItem(**a) for a in alerts]

    def mark_as_read(self, alert_id: str, user_id: str) -> Optional[AlertItem]:
        alert = store.mark_alert_read(alert_id, user_id)
        return AlertItem(**alert) if alert else None

    def delete_alert(self, alert_id: str, user_id: str) -> bool:
        return store.delete_alert(alert_id, user_id)


alert_service = AlertService()
