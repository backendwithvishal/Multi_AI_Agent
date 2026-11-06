"""
Backward-compatibility alias module for tripmate.services.price_watch_service.
"""

from tripmate.services.price_watch_service import (
    PriceWatchService,
    WatchlistService,
    price_watch_service,
    watchlist_service,
)

__all__ = [
    "PriceWatchService",
    "price_watch_service",
    "WatchlistService",
    "watchlist_service",
]
