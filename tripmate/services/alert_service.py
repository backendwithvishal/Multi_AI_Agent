"""
Backward-compatibility alias module for tripmate.services.notification_service.
"""

from tripmate.services.notification_service import (
    AlertService,
    NotificationService,
    alert_service,
    notification_service,
)

__all__ = [
    "NotificationService",
    "notification_service",
    "AlertService",
    "alert_service",
]
