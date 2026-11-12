"""
Backward-compatibility alias module for tripmate.api.v1.routes.notifications.
"""

from tripmate.api.v1.routes.notifications import (
    create_alert,
    delete_alert,
    legacy_router,
    list_alerts,
    mark_read,
    price_alerts_router,
)
from tripmate.api.v1.routes.notifications import (
    legacy_router as router,
)

__all__ = [
    "router",
    "price_alerts_router",
    "legacy_router",
    "list_alerts",
    "create_alert",
    "mark_read",
    "delete_alert",
]
