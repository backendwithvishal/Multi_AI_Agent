"""
Repository Pattern Module

Exposes repository interfaces and concrete implementations.
"""

from tripmate.repositories.interfaces import (
    IAlertRepository,
    IAssetRepository,
    IAuditLogRepository,
    IBookingRepository,
    IItineraryRepository,
    IThreadOwnerRepository,
    ITripRepository,
    IUserRepository,
    IWatchlistRepository,
    IWorkflowRunRepository,
)
from tripmate.repositories.store_repositories import (
    StoreAlertRepository,
    StoreAssetRepository,
    StoreAuditLogRepository,
    StoreBookingRepository,
    StoreItineraryRepository,
    StoreThreadOwnerRepository,
    StoreTripRepository,
    StoreUserRepository,
    StoreWatchlistRepository,
    StoreWorkflowRunRepository,
    alert_repository,
    asset_repository,
    audit_log_repository,
    booking_repository,
    itinerary_repository,
    thread_owner_repository,
    trip_repository,
    user_repository,
    watchlist_repository,
    workflow_run_repository,
)

__all__ = [
    "IUserRepository",
    "IWatchlistRepository",
    "IAlertRepository",
    "IAssetRepository",
    "IThreadOwnerRepository",
    "IBookingRepository",
    "ITripRepository",
    "IItineraryRepository",
    "IWorkflowRunRepository",
    "IAuditLogRepository",
    "StoreUserRepository",
    "StoreWatchlistRepository",
    "StoreAlertRepository",
    "StoreAssetRepository",
    "StoreThreadOwnerRepository",
    "StoreBookingRepository",
    "StoreTripRepository",
    "StoreItineraryRepository",
    "StoreWorkflowRunRepository",
    "StoreAuditLogRepository",
    "user_repository",
    "watchlist_repository",
    "alert_repository",
    "asset_repository",
    "thread_owner_repository",
    "booking_repository",
    "trip_repository",
    "itinerary_repository",
    "workflow_run_repository",
    "audit_log_repository",
]

