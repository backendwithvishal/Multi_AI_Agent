"""
Alert Notification Domain Service (Refactored with CQRS & Repository Patterns)

Manages travel price alerts, weather alerts, flight schedule notifications, and read statuses.
Routes mutations through Command Handlers and read requests through Query Handlers.
"""

from typing import List, Optional
from tripmate.cqrs.commands import (
    CreateAlertCommand,
    DeleteAlertCommand,
    MarkAlertReadCommand,
)
from tripmate.cqrs.handlers import AlertCommandHandlers, AlertQueryHandlers
from tripmate.cqrs.queries import ListAlertsQuery
from tripmate.repositories.interfaces import IAlertRepository
from tripmate.repositories.store_repositories import alert_repository
from tripmate.schemas import AlertCreateRequest, AlertItem


class AlertService:
    """Service managing platform alert notifications using CQRS."""

    def __init__(
        self,
        command_handler: Optional[AlertCommandHandlers] = None,
        query_handler: Optional[AlertQueryHandlers] = None,
        repo: Optional[IAlertRepository] = None,
    ):
        repository = repo or alert_repository
        self._command_handler = command_handler or AlertCommandHandlers(repository)
        self._query_handler = query_handler or AlertQueryHandlers(repository)

    def create_alert(self, user_id: str, req: AlertCreateRequest) -> AlertItem:
        """Executes CreateAlertCommand to persist a new notification alert."""
        cmd = CreateAlertCommand(
            user_id=user_id,
            title=req.title,
            message=req.message,
            alert_type=req.alert_type,
            severity=req.severity,
            watchlist_id=req.watchlist_id,
        )
        alert_data = self._command_handler.handle_create(cmd)
        return AlertItem(**alert_data)

    def list_alerts(self, user_id: str) -> List[AlertItem]:
        """Executes ListAlertsQuery (read-only)."""
        query = ListAlertsQuery(user_id=user_id)
        alerts = self._query_handler.handle_list(query)
        return [AlertItem(**a) for a in alerts]

    def mark_as_read(self, alert_id: str, user_id: str) -> Optional[AlertItem]:
        """Executes MarkAlertReadCommand to update alert read status."""
        cmd = MarkAlertReadCommand(alert_id=alert_id, user_id=user_id)
        alert = self._command_handler.handle_mark_read(cmd)
        return AlertItem(**alert) if alert else None

    def delete_alert(self, alert_id: str, user_id: str) -> bool:
        """Executes DeleteAlertCommand to remove an alert."""
        cmd = DeleteAlertCommand(alert_id=alert_id, user_id=user_id)
        return self._command_handler.handle_delete(cmd)


alert_service = AlertService()
