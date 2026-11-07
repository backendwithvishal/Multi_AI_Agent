"""
Repository Interfaces (Contracts)

Defines explicit repository contracts separating business logic from persistence.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class IUserRepository(ABC):
    """Repository interface for User accounts and Authentication state."""

    @abstractmethod
    def create(self, username: str, email: str, password_hash: str, role: str = "user") -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def get_by_username_or_email(self, identifier: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def list_all(self) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def create_password_reset_token(self, email: str) -> Optional[str]:
        pass

    @abstractmethod
    def verify_and_consume_reset_token(self, token: str, new_password_hash: str) -> bool:
        pass


class IWatchlistRepository(ABC):
    """Repository interface for Travel Watchlists."""

    @abstractmethod
    def create(
        self,
        user_id: str,
        title: str,
        target_type: str,
        target_value: str,
        threshold_price: Optional[float] = None,
        notes: str = "",
    ) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_by_id(self, item_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def list_by_user(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def delete(self, item_id: str, user_id: Optional[str] = None) -> bool:
        pass


class IAlertRepository(ABC):
    """Repository interface for Notification Alerts."""

    @abstractmethod
    def create(
        self,
        user_id: str,
        title: str,
        message: str,
        alert_type: str = "price_drop",
        severity: str = "info",
        watchlist_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        pass

    @abstractmethod
    def list_by_user(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def mark_as_read(self, alert_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def delete(self, alert_id: str, user_id: Optional[str] = None) -> bool:
        pass


class IAssetRepository(ABC):
    """Repository interface for Travel Assets and Documents."""

    @abstractmethod
    def create(
        self,
        user_id: str,
        name: str,
        asset_type: str,
        trip_id: Optional[str] = None,
        content_uri: Optional[str] = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_by_id(self, asset_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def list_by_user(self, user_id: Optional[str] = None, trip_id: Optional[str] = None) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def delete(self, asset_id: str, user_id: Optional[str] = None) -> bool:
        pass


class IThreadOwnerRepository(ABC):
    """Repository interface for Thread Ownership mapping."""

    @abstractmethod
    def register_owner(self, thread_id: str, user_id: str) -> None:
        pass

    @abstractmethod
    def get_owner(self, thread_id: str) -> Optional[str]:
        pass


class IBookingRepository(ABC):
    """Repository interface for GDS Fare Price Locks and Reservations."""

    @abstractmethod
    def lock_price(self, offer_id: str, offer_type: str, total_price: float, currency: str = "USD") -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_price_lock(self, lock_id: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def create_reservation(
        self,
        user_id: str,
        lock_id: str,
        passenger_name: str,
        passenger_email: str,
        special_requests: str = "",
    ) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_reservation(self, booking_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        pass
