"""
CQRS Pattern: Queries (Read-Only Data Retrieval Operations)

Defines explicit query objects that retrieve state without causing any side effects or mutations.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class GetWatchlistQuery:
    """Query to fetch a single watchlist by ID."""
    item_id: str
    user_id: str


@dataclass(frozen=True)
class ListWatchlistsQuery:
    """Query to list all watchlists for a user."""
    user_id: str


@dataclass(frozen=True)
class ListAlertsQuery:
    """Query to list all alerts for a user."""
    user_id: str


@dataclass(frozen=True)
class GetAssetQuery:
    """Query to fetch a travel asset by ID."""
    asset_id: str
    user_id: str


@dataclass(frozen=True)
class ListAssetsQuery:
    """Query to list travel assets for a user or trip."""
    user_id: str
    trip_id: Optional[str] = None


@dataclass(frozen=True)
class GetRunDetailsQuery:
    """Query to fetch execution telemetry for a workflow run."""
    run_id: str


@dataclass(frozen=True)
class GetRunMetricsQuery:
    """Query to fetch token and latency metrics for a workflow run."""
    run_id: str
