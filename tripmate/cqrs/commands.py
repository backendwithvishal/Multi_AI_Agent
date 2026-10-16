"""
CQRS Pattern: Commands (State-Changing Operations)

Defines explicit command objects for operations that mutate platform state.
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class CreateWatchlistCommand:
    """Command to create a travel price watchlist."""
    user_id: str
    title: str
    target_type: str
    target_value: str
    threshold_price: Optional[float] = None
    notes: str = ""


@dataclass(frozen=True)
class DeleteWatchlistCommand:
    """Command to delete an existing watchlist."""
    item_id: str
    user_id: str


@dataclass(frozen=True)
class CreateAlertCommand:
    """Command to create a new notification alert."""
    user_id: str
    title: str
    message: str
    alert_type: str = "price_drop"
    severity: str = "info"
    watchlist_id: Optional[str] = None


@dataclass(frozen=True)
class MarkAlertReadCommand:
    """Command to mark an alert as read."""
    alert_id: str
    user_id: str


@dataclass(frozen=True)
class DeleteAlertCommand:
    """Command to delete an alert."""
    alert_id: str
    user_id: str


@dataclass(frozen=True)
class CreateAssetCommand:
    """Command to create a travel asset or document."""
    user_id: str
    name: str
    asset_type: str
    trip_id: Optional[str] = None
    content_uri: Optional[str] = ""
    metadata: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class DeleteAssetCommand:
    """Command to delete a travel asset."""
    asset_id: str
    user_id: str


@dataclass(frozen=True)
class ExecuteTravelPlanCommand:
    """Command to start a multi-agent travel planning execution."""
    user_input: str
    thread_id: Optional[str] = None
    user_id: Optional[str] = None


@dataclass(frozen=True)
class ResumeTravelPlanCommand:
    """Command to resume a paused HITL workflow."""
    thread_id: str
    approved: bool
    feedback: str = ""
    user_id: Optional[str] = None
