"""
Repository Pattern Module

Exposes repository interfaces and concrete implementations.
"""

from tripmate.repositories.interfaces import (
    IAlertRepository,
    IAssetRepository,
    IBookingRepository,
    IThreadOwnerRepository,
    IUserRepository,
    IWatchlistRepository,
)
from tripmate.repositories.store_repositories import (
    StoreAlertRepository,
    StoreAssetRepository,
    StoreBookingRepository,
    StoreThreadOwnerRepository,
    StoreUserRepository,
    StoreWatchlistRepository,
    alert_repository,
    asset_repository,
    booking_repository,
    thread_owner_repository,
    user_repository,
    watchlist_repository,
)

__all__ = [
    "IUserRepository",
    "IWatchlistRepository",
    "IAlertRepository",
    "IAssetRepository",
    "IThreadOwnerRepository",
    "IBookingRepository",
    "StoreUserRepository",
    "StoreWatchlistRepository",
    "StoreAlertRepository",
    "StoreAssetRepository",
    "StoreThreadOwnerRepository",
    "StoreBookingRepository",
    "user_repository",
    "watchlist_repository",
    "alert_repository",
    "asset_repository",
    "thread_owner_repository",
    "booking_repository",
]
