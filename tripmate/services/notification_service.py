"""
Travel Alert & Notification Domain Service

Manages travel price alerts, weather alerts, flight schedule notifications, and read statuses.
"""

from typing import List, Optional

from tripmate.database.store import store
from tripmate.schemas import AlertCreateRequest, AlertItem


class NotificationService:
    """Service managing platform alert notifications."""

    def __init__(self, data_store=None):
        self._store = data_store or store

    def create_alert(self, user_id: str, req: AlertCreateRequest) -> AlertItem:
        alert_data = self._store.create_alert(
            user_id=user_id,
            title=req.title,
            message=req.message,
            alert_type=req.alert_type,
            severity=req.severity,
            watchlist_id=req.watchlist_id,
        )
        return AlertItem(**alert_data)

    def list_alerts(self, user_id: str) -> List[AlertItem]:
        alerts = self._store.list_alerts(user_id=user_id)
        return [AlertItem(**a) for a in alerts]

    def mark_as_read(self, alert_id: str, user_id: str) -> Optional[AlertItem]:
        alert = self._store.mark_alert_read(alert_id=alert_id, user_id=user_id)
        return AlertItem(**alert) if alert else None

    def delete_alert(self, alert_id: str, user_id: str) -> bool:
        return self._store.delete_alert(alert_id=alert_id, user_id=user_id)


notification_service = NotificationService()
AlertService = NotificationService
alert_service = notification_service
