"""
Concrete Repository Implementations

Provides DataStore-backed and isolated in-memory implementations for all repository contracts.
Supports dependency injection into application services and mock-based unit testing.
"""

import json
import logging
import secrets
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from tripmate.database import get_db_pool
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

logger = logging.getLogger("tripmate.repositories")


def _format_dt(dt: Any) -> str:
    if isinstance(dt, datetime):
        return dt.isoformat()
    return str(dt)


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
    """Booking repository managing GDS fare locks and reservations with PostgreSQL persistence and in-memory fallback."""

    def __init__(self):
        self._reservations: Dict[str, Dict[str, Any]] = {}
        self._price_locks: Dict[str, Dict[str, Any]] = {}

    def lock_price(
        self,
        offer_id: str,
        offer_type: str,
        total_price: float,
        currency: str = "USD",
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        lock_id = f"lock_{secrets.token_hex(8)}"
        expires_at = int(time.time()) + 900  # 15 minutes
        now_dt = datetime.now(timezone.utc)

        pool = get_db_pool()
        if pool:
            try:
                with pool.connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO price_locks (id, user_id, offer_id, offer_type, total_price, currency, status, expires_at, created_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                            RETURNING id, user_id, offer_id, offer_type, total_price, currency, status, expires_at;
                            """,
                            (
                                lock_id,
                                user_id,
                                offer_id,
                                offer_type,
                                total_price,
                                currency,
                                "ACTIVE",
                                expires_at,
                                now_dt,
                            ),
                        )
                        row = cur.fetchone()
                    conn.commit()
                    if row:
                        record = {
                            "lock_id": row["id"],
                            "offer_id": row["offer_id"],
                            "offer_type": row["offer_type"],
                            "locked_price": float(row["total_price"]),
                            "currency": row["currency"],
                            "expires_at": int(row["expires_at"]),
                            "status": row["status"],
                            "user_id": row.get("user_id"),
                        }
                        self._price_locks[lock_id] = record
                        return record
            except Exception as exc:
                logger.warning(f"PostgreSQL lock_price fallback to memory: {exc}")

        record = {
            "lock_id": lock_id,
            "offer_id": offer_id,
            "offer_type": offer_type,
            "locked_price": total_price,
            "currency": currency,
            "expires_at": expires_at,
            "status": "LOCKED",
            "user_id": user_id,
        }
        self._price_locks[lock_id] = record
        return record

    def get_price_lock(self, lock_id: str) -> Optional[Dict[str, Any]]:
        pool = get_db_pool()
        if pool:
            try:
                with pool.connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT id, user_id, offer_id, offer_type, total_price, currency, status, expires_at FROM price_locks WHERE id = %s;",
                            (lock_id,),
                        )
                        row = cur.fetchone()
                        if row:
                            return {
                                "lock_id": row["id"],
                                "offer_id": row["offer_id"],
                                "offer_type": row["offer_type"],
                                "locked_price": float(row["total_price"]),
                                "currency": row["currency"],
                                "expires_at": int(row["expires_at"]),
                                "status": row["status"],
                                "user_id": row.get("user_id"),
                            }
            except Exception as exc:
                logger.warning(f"PostgreSQL get_price_lock fallback to memory: {exc}")

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
        if lock.get("user_id") and lock["user_id"] != user_id:
            raise ValueError(f"Price lock '{lock_id}' does not belong to user '{user_id}'.")
        if lock["expires_at"] < time.time():
            raise ValueError(f"Price lock '{lock_id}' has expired. Please re-lock price.")
        if lock["status"] in ("BOOKED", "REDEEMED"):
            raise ValueError(f"Price lock '{lock_id}' has already been redeemed.")

        booking_id = f"bk_{uuid.uuid4().hex[:10]}"
        pnr_code = "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(6))
        now_dt = datetime.now(timezone.utc)

        pool = get_db_pool()
        if pool:
            try:
                with pool.connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "UPDATE price_locks SET status = 'BOOKED' WHERE id = %s AND status = 'ACTIVE';",
                            (lock_id,),
                        )
                        cur.execute(
                            """
                            INSERT INTO bookings (id, user_id, offer_id, offer_type, total_price, currency, passenger_name, passenger_email, special_requests, gds_pnr, status, created_at, updated_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                            """,
                            (
                                booking_id,
                                user_id,
                                lock["offer_id"],
                                lock["offer_type"],
                                lock["locked_price"],
                                lock["currency"],
                                passenger_name,
                                passenger_email,
                                special_requests,
                                pnr_code,
                                "CONFIRMED",
                                now_dt,
                                now_dt,
                            ),
                        )
                    conn.commit()
            except Exception as exc:
                logger.warning(f"PostgreSQL create_reservation fallback to memory: {exc}")

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
        pool = get_db_pool()
        if pool:
            try:
                with pool.connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT id, user_id, offer_id, offer_type, total_price, currency, passenger_name, passenger_email, special_requests, gds_pnr, status, created_at FROM bookings WHERE id = %s;",
                            (booking_id,),
                        )
                        row = cur.fetchone()
                        if row:
                            if user_id and row.get("user_id") != user_id:
                                return None
                            return {
                                "booking_id": row["id"],
                                "pnr_code": row.get("gds_pnr", ""),
                                "user_id": row.get("user_id"),
                                "offer_id": row["offer_id"],
                                "offer_type": row["offer_type"],
                                "amount_paid": float(row["total_price"]),
                                "currency": row["currency"],
                                "passenger_name": row.get("passenger_name", ""),
                                "passenger_email": row.get("passenger_email", ""),
                                "special_requests": row.get("special_requests", ""),
                                "booking_status": row.get("status", "CONFIRMED"),
                                "created_at": _format_dt(row["created_at"]),
                            }
            except Exception as exc:
                logger.warning(f"PostgreSQL get_reservation fallback to memory: {exc}")

        res = self._reservations.get(booking_id)
        if not res:
            return None
        if user_id and res["user_id"] != user_id:
            return None
        return res


class StoreTripRepository(ITripRepository):
    """Trips repository with PostgreSQL persistence and in-memory fallback."""

    def __init__(self):
        self._trips: Dict[str, Dict[str, Any]] = {}

    def create(
        self,
        user_id: str,
        title: str,
        destination: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        budget: Optional[float] = None,
    ) -> Dict[str, Any]:
        trip_id = f"trip_{uuid.uuid4().hex[:12]}"
        now_dt = datetime.now(timezone.utc)
        record = {
            "id": trip_id,
            "user_id": user_id,
            "title": title,
            "destination": destination,
            "start_date": start_date,
            "end_date": end_date,
            "budget": float(budget) if budget is not None else None,
            "status": "PLANNING",
            "created_at": now_dt.isoformat(),
            "updated_at": now_dt.isoformat(),
        }

        pool = get_db_pool()
        if pool:
            try:
                with pool.connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO trips (id, user_id, title, destination, start_date, end_date, budget, status, created_at, updated_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                            """,
                            (
                                trip_id,
                                user_id,
                                title,
                                destination,
                                start_date,
                                end_date,
                                budget,
                                "PLANNING",
                                now_dt,
                                now_dt,
                            ),
                        )
                    conn.commit()
            except Exception as exc:
                logger.warning(f"PostgreSQL create trip failed: {exc}")

        self._trips[trip_id] = record
        return record

    def get_by_id(self, trip_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        pool = get_db_pool()
        if pool:
            try:
                with pool.connection() as conn:
                    with conn.cursor() as cur:
                        if user_id:
                            cur.execute(
                                "SELECT id, user_id, title, destination, start_date, end_date, budget, status, created_at, updated_at FROM trips WHERE id = %s AND user_id = %s;",
                                (trip_id, user_id),
                            )
                        else:
                            cur.execute(
                                "SELECT id, user_id, title, destination, start_date, end_date, budget, status, created_at, updated_at FROM trips WHERE id = %s;",
                                (trip_id,),
                            )
                        row = cur.fetchone()
                        if row:
                            return {
                                "id": row["id"],
                                "user_id": row["user_id"],
                                "title": row["title"],
                                "destination": row["destination"],
                                "start_date": row.get("start_date"),
                                "end_date": row.get("end_date"),
                                "budget": float(row["budget"]) if row.get("budget") is not None else None,
                                "status": row.get("status", "PLANNING"),
                                "created_at": _format_dt(row["created_at"]),
                                "updated_at": _format_dt(row["updated_at"]),
                            }
            except Exception as exc:
                logger.warning(f"PostgreSQL get_by_id trip failed: {exc}")

        trip = self._trips.get(trip_id)
        if trip and user_id and trip["user_id"] != user_id:
            return None
        return trip

    def list_by_user(self, user_id: str) -> List[Dict[str, Any]]:
        pool = get_db_pool()
        if pool:
            try:
                with pool.connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT id, user_id, title, destination, start_date, end_date, budget, status, created_at, updated_at FROM trips WHERE user_id = %s ORDER BY created_at DESC;",
                            (user_id,),
                        )
                        rows = cur.fetchall()
                        return [
                            {
                                "id": r["id"],
                                "user_id": r["user_id"],
                                "title": r["title"],
                                "destination": r["destination"],
                                "start_date": r.get("start_date"),
                                "end_date": r.get("end_date"),
                                "budget": float(r["budget"]) if r.get("budget") is not None else None,
                                "status": r.get("status", "PLANNING"),
                                "created_at": _format_dt(r["created_at"]),
                                "updated_at": _format_dt(r["updated_at"]),
                            }
                            for r in rows
                        ]
            except Exception as exc:
                logger.warning(f"PostgreSQL list_by_user trip failed: {exc}")

        return [t for t in self._trips.values() if t.get("user_id") == user_id]

    def update(self, trip_id: str, user_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        trip = self.get_by_id(trip_id, user_id)
        if not trip:
            return None

        now_dt = datetime.now(timezone.utc)
        pool = get_db_pool()
        if pool:
            try:
                set_clauses = ["updated_at = %s"]
                params: List[Any] = [now_dt]
                for col in ("title", "destination", "start_date", "end_date", "budget", "status"):
                    if col in updates:
                        set_clauses.append(f"{col} = %s")
                        params.append(updates[col])
                params.extend([trip_id, user_id])

                with pool.connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            f"UPDATE trips SET {', '.join(set_clauses)} WHERE id = %s AND user_id = %s;",
                            params,
                        )
                    conn.commit()
            except Exception as exc:
                logger.warning(f"PostgreSQL update trip failed: {exc}")

        trip = self._trips.get(trip_id) or trip
        for k, v in updates.items():
            if k in ("title", "destination", "start_date", "end_date", "budget", "status"):
                trip[k] = v
        trip["updated_at"] = now_dt.isoformat()
        self._trips[trip_id] = trip
        return trip

    def delete(self, trip_id: str, user_id: str) -> bool:
        trip = self.get_by_id(trip_id, user_id)
        if not trip:
            return False

        pool = get_db_pool()
        if pool:
            try:
                with pool.connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("DELETE FROM trips WHERE id = %s AND user_id = %s;", (trip_id, user_id))
                    conn.commit()
            except Exception as exc:
                logger.warning(f"PostgreSQL delete trip failed: {exc}")

        self._trips.pop(trip_id, None)
        return True


class StoreItineraryRepository(IItineraryRepository):
    """Itinerary repository with PostgreSQL persistence and in-memory fallback."""

    def __init__(self):
        self._itineraries: Dict[str, Dict[str, Any]] = {}

    def create(
        self,
        trip_id: str,
        user_id: str,
        content: Optional[str] = None,
        day_plans: Optional[Dict[str, Any]] = None,
        status: str = "DRAFT",
    ) -> Dict[str, Any]:
        itinerary_id = f"itin_{uuid.uuid4().hex[:12]}"
        now_dt = datetime.now(timezone.utc)
        record = {
            "id": itinerary_id,
            "trip_id": trip_id,
            "user_id": user_id,
            "content": content,
            "day_plans": day_plans,
            "status": status,
            "created_at": now_dt.isoformat(),
            "updated_at": now_dt.isoformat(),
        }

        pool = get_db_pool()
        if pool:
            try:
                with pool.connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO itineraries (id, trip_id, user_id, content, day_plans, status, created_at, updated_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
                            """,
                            (
                                itinerary_id,
                                trip_id,
                                user_id,
                                content,
                                json.dumps(day_plans) if day_plans else None,
                                status,
                                now_dt,
                                now_dt,
                            ),
                        )
                    conn.commit()
            except Exception as exc:
                logger.warning(f"PostgreSQL create itinerary failed: {exc}")

        self._itineraries[itinerary_id] = record
        return record

    def get_by_id(self, itinerary_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        pool = get_db_pool()
        if pool:
            try:
                with pool.connection() as conn:
                    with conn.cursor() as cur:
                        if user_id:
                            cur.execute(
                                "SELECT id, trip_id, user_id, content, day_plans, status, created_at, updated_at FROM itineraries WHERE id = %s AND user_id = %s;",
                                (itinerary_id, user_id),
                            )
                        else:
                            cur.execute(
                                "SELECT id, trip_id, user_id, content, day_plans, status, created_at, updated_at FROM itineraries WHERE id = %s;",
                                (itinerary_id,),
                            )
                        row = cur.fetchone()
                        if row:
                            return {
                                "id": row["id"],
                                "trip_id": row["trip_id"],
                                "user_id": row["user_id"],
                                "content": row.get("content"),
                                "day_plans": row.get("day_plans"),
                                "status": row.get("status", "DRAFT"),
                                "created_at": _format_dt(row["created_at"]),
                                "updated_at": _format_dt(row["updated_at"]),
                            }
            except Exception as exc:
                logger.warning(f"PostgreSQL get_by_id itinerary failed: {exc}")

        it = self._itineraries.get(itinerary_id)
        if it and user_id and it["user_id"] != user_id:
            return None
        return it

    def list_by_trip(self, trip_id: str, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        pool = get_db_pool()
        if pool:
            try:
                with pool.connection() as conn:
                    with conn.cursor() as cur:
                        if user_id:
                            cur.execute(
                                "SELECT id, trip_id, user_id, content, day_plans, status, created_at, updated_at FROM itineraries WHERE trip_id = %s AND user_id = %s ORDER BY created_at DESC;",
                                (trip_id, user_id),
                            )
                        else:
                            cur.execute(
                                "SELECT id, trip_id, user_id, content, day_plans, status, created_at, updated_at FROM itineraries WHERE trip_id = %s ORDER BY created_at DESC;",
                                (trip_id,),
                            )
                        rows = cur.fetchall()
                        return [
                            {
                                "id": r["id"],
                                "trip_id": r["trip_id"],
                                "user_id": r["user_id"],
                                "content": r.get("content"),
                                "day_plans": r.get("day_plans"),
                                "status": r.get("status", "DRAFT"),
                                "created_at": _format_dt(r["created_at"]),
                                "updated_at": _format_dt(r["updated_at"]),
                            }
                            for r in rows
                        ]
            except Exception as exc:
                logger.warning(f"PostgreSQL list_by_trip failed: {exc}")

        res = [it for it in self._itineraries.values() if it.get("trip_id") == trip_id]
        if user_id:
            res = [it for it in res if it.get("user_id") == user_id]
        return res

    def update(self, itinerary_id: str, user_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        it = self.get_by_id(itinerary_id, user_id)
        if not it:
            return None
        now_dt = datetime.now(timezone.utc)
        it = self._itineraries.get(itinerary_id) or it
        for k, v in updates.items():
            if k in ("content", "day_plans", "status"):
                it[k] = v
        it["updated_at"] = now_dt.isoformat()
        self._itineraries[itinerary_id] = it
        return it

    def delete(self, itinerary_id: str, user_id: str) -> bool:
        it = self.get_by_id(itinerary_id, user_id)
        if not it:
            return False
        pool = get_db_pool()
        if pool:
            try:
                with pool.connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("DELETE FROM itineraries WHERE id = %s AND user_id = %s;", (itinerary_id, user_id))
                    conn.commit()
            except Exception as exc:
                logger.warning(f"PostgreSQL delete itinerary failed: {exc}")
        self._itineraries.pop(itinerary_id, None)
        return True


class StoreWorkflowRunRepository(IWorkflowRunRepository):
    """Workflow Run repository syncing with workflow_runs table and RUN_STORE."""

    def __init__(self):
        self._runs: Dict[str, Dict[str, Any]] = {}

    def create(
        self,
        run_id: str,
        user_id: Optional[str] = None,
        thread_id: Optional[str] = None,
        status: str = "RUNNING",
        query: Optional[str] = None,
        itinerary: Optional[str] = None,
        metrics: Optional[Dict[str, Any]] = None,
        events: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        now_dt = datetime.now(timezone.utc)
        record = {
            "run_id": run_id,
            "id": run_id,
            "user_id": user_id,
            "thread_id": thread_id,
            "status": status,
            "query": query,
            "itinerary": itinerary,
            "metrics": metrics or {},
            "events": events or [],
            "created_at": now_dt.isoformat(),
            "updated_at": now_dt.isoformat(),
        }

        pool = get_db_pool()
        if pool:
            try:
                with pool.connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO workflow_runs (id, user_id, thread_id, status, query, itinerary, metrics, events, created_at, updated_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (id) DO UPDATE SET
                                status = EXCLUDED.status,
                                itinerary = EXCLUDED.itinerary,
                                metrics = EXCLUDED.metrics,
                                events = EXCLUDED.events,
                                updated_at = EXCLUDED.updated_at;
                            """,
                            (
                                run_id,
                                user_id,
                                thread_id,
                                status,
                                query,
                                itinerary,
                                json.dumps(metrics) if metrics else None,
                                json.dumps(events) if events else None,
                                now_dt,
                                now_dt,
                            ),
                        )
                    conn.commit()
            except Exception as exc:
                logger.warning(f"PostgreSQL create workflow_run failed: {exc}")

        self._runs[run_id] = record
        return record

    def get_by_id(self, run_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        pool = get_db_pool()
        if pool:
            try:
                with pool.connection() as conn:
                    with conn.cursor() as cur:
                        if user_id:
                            cur.execute(
                                "SELECT id, user_id, thread_id, status, query, itinerary, metrics, events, created_at, updated_at FROM workflow_runs WHERE id = %s AND user_id = %s;",
                                (run_id, user_id),
                            )
                        else:
                            cur.execute(
                                "SELECT id, user_id, thread_id, status, query, itinerary, metrics, events, created_at, updated_at FROM workflow_runs WHERE id = %s;",
                                (run_id,),
                            )
                        row = cur.fetchone()
                        if row:
                            return {
                                "run_id": row["id"],
                                "id": row["id"],
                                "user_id": row.get("user_id"),
                                "thread_id": row.get("thread_id"),
                                "status": row.get("status", "RUNNING"),
                                "query": row.get("query"),
                                "itinerary": row.get("itinerary"),
                                "metrics": row.get("metrics") or {},
                                "events": row.get("events") or [],
                                "created_at": _format_dt(row["created_at"]),
                                "updated_at": _format_dt(row["updated_at"]),
                            }
            except Exception as exc:
                logger.warning(f"PostgreSQL get workflow_run failed: {exc}")

        run = self._runs.get(run_id)
        if run and user_id and run.get("user_id") != user_id:
            return None
        return run

    def list_all(self, user_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        pool = get_db_pool()
        if pool:
            try:
                with pool.connection() as conn:
                    with conn.cursor() as cur:
                        if user_id:
                            cur.execute(
                                "SELECT id, user_id, thread_id, status, query, itinerary, metrics, events, created_at, updated_at FROM workflow_runs WHERE user_id = %s ORDER BY created_at DESC LIMIT %s;",
                                (user_id, limit),
                            )
                        else:
                            cur.execute(
                                "SELECT id, user_id, thread_id, status, query, itinerary, metrics, events, created_at, updated_at FROM workflow_runs ORDER BY created_at DESC LIMIT %s;",
                                (limit,),
                            )
                        rows = cur.fetchall()
                        return [
                            {
                                "run_id": r["id"],
                                "id": r["id"],
                                "user_id": r.get("user_id"),
                                "thread_id": r.get("thread_id"),
                                "status": r.get("status", "RUNNING"),
                                "query": r.get("query"),
                                "itinerary": r.get("itinerary"),
                                "metrics": r.get("metrics") or {},
                                "events": r.get("events") or [],
                                "created_at": _format_dt(r["created_at"]),
                                "updated_at": _format_dt(r["updated_at"]),
                            }
                            for r in rows
                        ]
            except Exception as exc:
                logger.warning(f"PostgreSQL list workflow_runs failed: {exc}")

        res = list(self._runs.values())
        if user_id:
            res = [r for r in res if r.get("user_id") == user_id]
        return res[:limit]

    def update(self, run_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        run = self.get_by_id(run_id)
        if not run:
            return None
        now_dt = datetime.now(timezone.utc)
        pool = get_db_pool()
        if pool:
            try:
                set_clauses = ["updated_at = %s"]
                params: List[Any] = [now_dt]
                for col in ("status", "query", "itinerary"):
                    if col in updates:
                        set_clauses.append(f"{col} = %s")
                        params.append(updates[col])
                if "metrics" in updates:
                    set_clauses.append("metrics = %s")
                    params.append(json.dumps(updates["metrics"]))
                if "events" in updates:
                    set_clauses.append("events = %s")
                    params.append(json.dumps(updates["events"]))
                params.append(run_id)

                with pool.connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            f"UPDATE workflow_runs SET {', '.join(set_clauses)} WHERE id = %s;",
                            params,
                        )
                    conn.commit()
            except Exception as exc:
                logger.warning(f"PostgreSQL update workflow_run failed: {exc}")

        run = self._runs.get(run_id) or run
        run.update(updates)
        run["updated_at"] = now_dt.isoformat()
        self._runs[run_id] = run
        return run


class StoreAuditLogRepository(IAuditLogRepository):
    """Audit Log repository storing events in PostgreSQL with in-memory fallback."""

    def __init__(self):
        self._logs: List[Dict[str, Any]] = []

    def record(
        self,
        actor: str,
        action: str,
        target_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        status: str = "success",
        details: Optional[Dict[str, Any]] = None,
        prev_hash: Optional[str] = None,
        hash_val: Optional[str] = None,
    ) -> Dict[str, Any]:
        log_id = f"aud_{uuid.uuid4().hex[:12]}"
        now_dt = datetime.now(timezone.utc)
        record = {
            "id": log_id,
            "actor": actor,
            "action": action,
            "target_id": target_id,
            "ip_address": ip_address,
            "status": status,
            "details": details or {},
            "prev_hash": prev_hash,
            "hash": hash_val,
            "created_at": now_dt.isoformat(),
        }

        pool = get_db_pool()
        if pool:
            try:
                with pool.connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO audit_logs (id, actor, action, target_id, ip_address, status, details, prev_hash, hash, created_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                            """,
                            (
                                log_id,
                                actor,
                                action,
                                target_id,
                                ip_address,
                                status,
                                json.dumps(details) if details else None,
                                prev_hash,
                                hash_val,
                                now_dt,
                            ),
                        )
                    conn.commit()
            except Exception as exc:
                logger.warning(f"PostgreSQL record audit log failed: {exc}")

        self._logs.append(record)
        return record

    def list_logs(self, limit: int = 100, actor: Optional[str] = None) -> List[Dict[str, Any]]:
        pool = get_db_pool()
        if pool:
            try:
                with pool.connection() as conn:
                    with conn.cursor() as cur:
                        if actor:
                            cur.execute(
                                "SELECT id, actor, action, target_id, ip_address, status, details, prev_hash, hash, created_at FROM audit_logs WHERE actor = %s ORDER BY created_at DESC LIMIT %s;",
                                (actor, limit),
                            )
                        else:
                            cur.execute(
                                "SELECT id, actor, action, target_id, ip_address, status, details, prev_hash, hash, created_at FROM audit_logs ORDER BY created_at DESC LIMIT %s;",
                                (limit,),
                            )
                        rows = cur.fetchall()
                        return [
                            {
                                "id": r["id"],
                                "actor": r["actor"],
                                "action": r["action"],
                                "target_id": r.get("target_id"),
                                "ip_address": r.get("ip_address"),
                                "status": r.get("status", "success"),
                                "details": r.get("details") or {},
                                "prev_hash": r.get("prev_hash"),
                                "hash": r.get("hash"),
                                "created_at": _format_dt(r["created_at"]),
                            }
                            for r in rows
                        ]
            except Exception as exc:
                logger.warning(f"PostgreSQL list audit logs failed: {exc}")

        logs = self._logs
        if actor:
            logs = [entry for entry in logs if entry.get("actor") == actor]
        return sorted(logs, key=lambda entry: entry.get("created_at", ""), reverse=True)[:limit]


# Default singleton instances for dependency injection
user_repository: IUserRepository = StoreUserRepository()
watchlist_repository: IWatchlistRepository = StoreWatchlistRepository()
alert_repository: IAlertRepository = StoreAlertRepository()
asset_repository: IAssetRepository = StoreAssetRepository()
thread_owner_repository: IThreadOwnerRepository = StoreThreadOwnerRepository()
booking_repository: IBookingRepository = StoreBookingRepository()
trip_repository: ITripRepository = StoreTripRepository()
itinerary_repository: IItineraryRepository = StoreItineraryRepository()
workflow_run_repository: IWorkflowRunRepository = StoreWorkflowRunRepository()
audit_log_repository: IAuditLogRepository = StoreAuditLogRepository()
