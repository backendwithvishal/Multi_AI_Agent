"""
Backward-compatibility alias module for tripmate.api.v1.routes.price_watches.
"""

from tripmate.api.v1.routes.price_watches import (
    create_watchlist,
    delete_watchlist,
    get_watchlist,
    legacy_router,
    list_watchlists,
)
from tripmate.api.v1.routes.price_watches import (
    legacy_router as router,
)

__all__ = [
    "router",
    "legacy_router",
    "list_watchlists",
    "create_watchlist",
    "get_watchlist",
    "delete_watchlist",
]
