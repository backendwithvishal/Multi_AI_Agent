"""
Concrete Repository Implementations

Provides DataStore-backed and isolated in-memory implementations for all repository contracts.
Supports dependency injection into application services and mock-based unit testing.
"""

import secrets
import time
import uuid
from typing import Any, Dict, List, Optional

from tripmate.repositories.interfaces import (
    IAlertRepository,
    IAssetRepository,
    IBookingRepository,
    IThreadOwnerRepository,
    IUserRepository,
    IWatchlistRepository,
)


class StoreUserRepository(IUserRepository):
    """User repository delegating to unified DataStore."""

    def __init__(self, data_store: Any = None):
        self._store = data_store

    @property
    def store(self):
        if self._store is None:
            from tripmate.database.store import store
            self._store = store
        return self._store

    def create(self, username: str, email: str, password_hash: str, role: str = "user") -> Dict[str, Any]:
        return self.store.create_user(username, email, password_hash, role)

    def get_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        return self.store.get_user_by_id(user_id)

    def get_by_username_or_email(self, identifier: str) -> Optional[Dict[str, Any]]:
        return self.store.get_user_by_username_or_email(identifier)

    def list_all(self) -> List[Dict[str, Any]]:
        return self.store.list_users()

    def create_password_reset_token(self, email: str) -> Optional[str]:
        return self.store.create_password_reset_token(email)

    def verify_and_consume_reset_token(self, token: str, new_password_hash: str) -> bool:
        return self.store.verify_and_consume_reset_token(token, new_password_hash)


class StoreWatchlistRepository(IWatchlistRepository):
    """Watchlist repository delegating to unified DataStore."""

    def __init__(self, data_store: Any = None):
        self._store = data_store

    @property
    def store(self):
        if self._store is None:
            from tripmate.database.store import store
            self._store = store
        return self._store

    def create(
        self,
        user_id: str,
        title: str,
        target_type: str,
        target_value: str,
        threshold_price: Optional[float] = None,
        notes: str = "",
    ) -> Dict[str, Any]:
        return self.store.create_watchlist(
            user_id=user_id,
            title=title,
            target_type=target_type,
            target_value=target_value,
            threshold_price=threshold_price,
            notes=notes,
        )

    def get_by_id(self, item_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        return self.store.get_watchlist(item_id, user_id)

    def list_by_user(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        return self.store.list_watchlists(user_id)

    def delete(self, item_id: str, user_id: Optional[str] = None) -> bool:
        return self.store.delete_watchlist(item_id, user_id)


class StoreAlertRepository(IAlertRepository):
    """Alert repository delegating to unified DataStore."""

    def __init__(self, data_store: Any = None):
        self._store = data_store

    @property
    def store(self):
        if self._store is None:
            from tripmate.database.store import store
            self._store = store
        return self._store

    def create(
        self,
        user_id: str,
        title: str,
        message: str,
        alert_type: str = "price_drop",
        severity: str = "info",
        watchlist_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self.store.create_alert(
            user_id=user_id,
            title=title,
            message=message,
            alert_type=alert_type,
            severity=severity,
            watchlist_id=watchlist_id,
        )

    def list_by_user(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        return self.store.list_alerts(user_id)

    def mark_as_read(self, alert_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        return self.store.mark_alert_read(alert_id, user_id)

    def delete(self, alert_id: str, user_id: Optional[str] = None) -> bool:
        return self.store.delete_alert(alert_id, user_id)


class StoreAssetRepository(IAssetRepository):
    """Asset repository delegating to unified DataStore."""

    def __init__(self, data_store: Any = None):
        self._store = data_store

    @property
    def store(self):
        if self._store is None:
            from tripmate.database.store import store
            self._store = store
        return self._store

    def create(
        self,
        user_id: str,
        name: str,
        asset_type: str,
        trip_id: Optional[str] = None,
        content_uri: Optional[str] = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self.store.create_asset(
            user_id=user_id,
            name=name,
            asset_type=asset_type,
            trip_id=trip_id,
            content_uri=content_uri,
            metadata=metadata,
        )

    def get_by_id(self, asset_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        return self.store.get_asset(asset_id, user_id)

    def list_by_user(self, user_id: Optional[str] = None, trip_id: Optional[str] = None) -> List[Dict[str, Any]]:
        return self.store.list_assets(user_id=user_id, trip_id=trip_id)

    def delete(self, asset_id: str, user_id: Optional[str] = None) -> bool:
        return self.store.delete_asset(asset_id, user_id)


class StoreThreadOwnerRepository(IThreadOwnerRepository):
    """Thread owner repository delegating to unified DataStore."""

    def __init__(self, data_store: Any = None):
        self._store = data_store

    @property
    def store(self):
        if self._store is None:
            from tripmate.database.store import store
            self._store = store
        return self._store

    def register_owner(self, thread_id: str, user_id: str) -> None:
        self.store.register_thread_owner(thread_id, user_id)

    def get_owner(self, thread_id: str) -> Optional[str]:
        return self.store.get_thread_owner(thread_id)


class StoreBookingRepository(IBookingRepository):
    """Booking repository managing GDS fare locks and reservations."""

    def __init__(self):
        self._reservations: Dict[str, Dict[str, Any]] = {}
        self._price_locks: Dict[str, Dict[str, Any]] = {}

    def lock_price(self, offer_id: str, offer_type: str, total_price: float, currency: str = "USD") -> Dict[str, Any]:
        lock_id = f"lock_{secrets.token_hex(8)}"
        record = {
            "lock_id": lock_id,
            "offer_id": offer_id,
            "offer_type": offer_type,
            "locked_price": total_price,
            "currency": currency,
            "expires_at": int(time.time()) + 900,  # 15 minutes
            "status": "LOCKED",
        }
        self._price_locks[lock_id] = record
        return record

    def get_price_lock(self, lock_id: str) -> Optional[Dict[str, Any]]:
        return self._price_locks.get(lock_id)

    def create_reservation(
        self,
        user_id: str,
        lock_id: str,
        passenger_name: str,
        passenger_email: str,
        special_requests: str = "",
    ) -> Dict[str, Any]:
        lock = self.get_price_lock(lock_id)
        if not lock:
            raise ValueError(f"Price lock '{lock_id}' does not exist.")
        if lock["expires_at"] < time.time():
            raise ValueError(f"Price lock '{lock_id}' has expired. Please re-lock price.")
        if lock["status"] == "BOOKED":
            raise ValueError(f"Price lock '{lock_id}' has already been redeemed.")

        booking_id = f"bk_{uuid.uuid4().hex[:10]}"
        pnr_code = "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(6))

        reservation = {
            "booking_id": booking_id,
            "pnr_code": pnr_code,
            "user_id": user_id,
            "offer_id": lock["offer_id"],
            "offer_type": lock["offer_type"],
            "amount_paid": lock["locked_price"],
            "currency": lock["currency"],
            "passenger_name": passenger_name,
            "passenger_email": passenger_email,
            "special_requests": special_requests,
            "booking_status": "CONFIRMED",
            "created_at": time.time(),
        }

        lock["status"] = "BOOKED"
        self._reservations[booking_id] = reservation
        return reservation

    def get_reservation(self, booking_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        res = self._reservations.get(booking_id)
        if not res:
            return None
        if user_id and res["user_id"] != user_id:
            return None
        return res


# Default singleton instances for dependency injection
user_repository: IUserRepository = StoreUserRepository()
watchlist_repository: IWatchlistRepository = StoreWatchlistRepository()
alert_repository: IAlertRepository = StoreAlertRepository()
asset_repository: IAssetRepository = StoreAssetRepository()
thread_owner_repository: IThreadOwnerRepository = StoreThreadOwnerRepository()
booking_repository: IBookingRepository = StoreBookingRepository()
