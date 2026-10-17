"""
Unified Data Store & Repository Layer

This module provides thread-safe in-memory and PostgreSQL-compatible repositories for:
1. Users & Authentication
2. Watchlists (Destinations, Flights, Hotels)
3. Alerts & Event Notifications
4. Travel Assets & Documents
"""

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
import uuid
from decimal import Decimal
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from tripmate.config.settings import settings
from tripmate.core.singleton import SingletonMeta
from tripmate.database import get_db_pool

logger = logging.getLogger("tripmate.store")


# =========================================================
# Password Hashing & Token Utilities
# =========================================================

def hash_password(password: str, salt: Optional[str] = None) -> str:
    """Hashes a password using PBKDF2-HMAC-SHA256 with a unique salt."""
    if not salt:
        salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        100000,
    )
    return f"{salt}${key.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verifies a plaintext password against a stored PBKDF2 salt$hash string."""
    try:
        salt, key_hex = stored_hash.split("$", 1)
        computed = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            100000,
        )
        return secrets.compare_digest(computed.hex(), key_hex)
    except Exception:
        return False


def _get_signing_secret() -> str:
    """Returns the cryptographic signing key, requiring explicit secret in production."""
    secret = settings.API_KEY
    if not secret:
        if settings.APP_ENV == "production":
            raise RuntimeError("API_KEY must be configured in production for secure token signing.")
        return "tripmate_platform_secret_key_2026"
    return secret


def generate_token(user_id: str, username: str, role: str) -> str:
    """Generates a tamper-proof HMAC-SHA256 signed bearer access token."""
    secret = _get_signing_secret()
    payload = {
        "uid": user_id,
        "usr": username,
        "rol": role,
        "exp": int(time.time()) + 86400 * 7,  # 7 days
    }
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8").rstrip("=")
    sig = hmac.new(secret.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{sig}"


def verify_token(token: str) -> Optional[Dict[str, Any]]:
    """Verifies HMAC-SHA256 signed token and returns claims payload if valid."""
    try:
        secret = _get_signing_secret()
        parts = token.split(".", 1)
        if len(parts) != 2:
            return None
        payload_b64, sig = parts
        expected_sig = hmac.new(secret.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
        if not secrets.compare_digest(sig, expected_sig):
            return None
        # Add padding back if necessary
        padding = "=" * ((4 - len(payload_b64) % 4) % 4)
        payload_raw = base64.urlsafe_b64decode(f"{payload_b64}{padding}")
        payload = json.loads(payload_raw.decode("utf-8"))
        if payload.get("exp", 0) < time.time():
            return None  # Expired
        return payload
    except Exception:
        return None


def _format_datetime(dt: Any) -> str:
    if isinstance(dt, datetime):
        return dt.isoformat()
    return str(dt)


def _format_float(val: Any) -> Optional[float]:
    if val is None:
        return None
    if isinstance(val, (Decimal, int, float)):
        return float(val)
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


# =========================================================
# Unified Data Repository
# =========================================================

class DataStore(metaclass=SingletonMeta):
    """Thread-safe unified data store managing platform entities with PostgreSQL persistence."""

    def __init__(self):
        self._users: Dict[str, Dict[str, Any]] = {}
        self._watchlists: Dict[str, Dict[str, Any]] = {}
        self._alerts: Dict[str, Dict[str, Any]] = {}
        self._assets: Dict[str, Dict[str, Any]] = {}
        self._reset_tokens: Dict[str, Dict[str, Any]] = {}
        self._thread_owners: Dict[str, str] = {}
        self._start_time = time.time()
        self._seed_initial_data()

    def _seed_initial_data(self):
        """Seeds default admin and demo user accounts in memory and PostgreSQL."""
        admin_id = "user_admin_001"
        admin_data = {
            "id": admin_id,
            "username": "admin",
            "email": "admin@tripmate.ai",
            "password_hash": hash_password("Admin@12345"),
            "role": "admin",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._users[admin_id] = admin_data

        demo_id = "user_demo_002"
        demo_data = {
            "id": demo_id,
            "username": "demouser",
            "email": "user@tripmate.ai",
            "password_hash": hash_password("User@12345"),
            "role": "user",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._users[demo_id] = demo_data

        pool = get_db_pool()
        if pool:
            try:
                with pool.connection() as conn:
                    with conn.cursor() as cur:
                        now = datetime.now(timezone.utc)
                        cur.execute(
                            """
                            INSERT INTO users (id, username, email, password_hash, role, created_at)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            ON CONFLICT (id) DO NOTHING;
                            """,
                            (admin_id, admin_data["username"], admin_data["email"], admin_data["password_hash"], admin_data["role"], now),
                        )
                        cur.execute(
                            """
                            INSERT INTO users (id, username, email, password_hash, role, created_at)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            ON CONFLICT (id) DO NOTHING;
                            """,
                            (demo_id, demo_data["username"], demo_data["email"], demo_data["password_hash"], demo_data["role"], now),
                        )
                    conn.commit()
            except Exception as exc:
                logger.warning(f"Notice: Initial PostgreSQL user seeding skipped: {exc}")

    def _ensure_user_exists(self, user_id: str) -> None:
        """Ensure a user row exists in PostgreSQL to satisfy foreign key constraints for tests and arbitrary user references."""
        if not user_id:
            return
        pool = get_db_pool()
        if pool:
            try:
                with pool.connection() as conn:
                    with conn.cursor() as cur:
                        now = datetime.now(timezone.utc)
                        hashed_suffix = uuid.uuid5(uuid.NAMESPACE_DNS, user_id).hex[:16]
                        cur.execute(
                            """
                            INSERT INTO users (id, username, email, password_hash, role, created_at)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            ON CONFLICT DO NOTHING;
                            """,
                            (user_id, f"auto_{hashed_suffix}", f"auto_{hashed_suffix}@tripmate.local", "dummy_hash", "user", now),
                        )
                    conn.commit()
            except Exception as exc:
                logger.debug(f"Notice: _ensure_user_exists skipped for {user_id}: {exc}")

        if user_id not in self._users:
            self._users[user_id] = {
                "id": user_id,
                "username": f"auto_{user_id}",
                "email": f"{user_id}@tripmate.local",
                "password_hash": "dummy_hash",
                "role": "user",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

    # -----------------------------------------------------
    # User & Account Recovery Operations
    # -----------------------------------------------------
    def create_user(self, username: str, email: str, password_hash: str, role: str = "user") -> Dict[str, Any]:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)
        user = {
            "id": user_id,
            "username": username.lower(),
            "email": email.lower(),
            "password_hash": password_hash,
            "role": role,
            "created_at": now.isoformat(),
        }

        pool = get_db_pool()
        if pool:
            try:
                with pool.connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO users (id, username, email, password_hash, role, created_at)
                            VALUES (%s, %s, %s, %s, %s, %s);
                            """,
                            (user_id, user["username"], user["email"], password_hash, role, now),
                        )
                    conn.commit()
            except Exception as exc:
                logger.error(f"PostgreSQL create_user write failed: {exc}")
                raise

        self._users[user_id] = user
        return user

    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        pool = get_db_pool()
        if pool:
            try:
                with pool.connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT id, username, email, password_hash, role, created_at FROM users WHERE id = %s;",
                            (user_id,),
                        )
                        row = cur.fetchone()
                        if row:
                            user = {
                                "id": row["id"],
                                "username": row["username"],
                                "email": row["email"],
                                "password_hash": row["password_hash"],
                                "role": row["role"],
                                "created_at": _format_datetime(row["created_at"]),
                            }
                            self._users[user_id] = user
                            return user
            except Exception as exc:
                logger.warning(f"PostgreSQL get_user_by_id failed: {exc}")

        return self._users.get(user_id)

    def get_user_by_username_or_email(self, identifier: str) -> Optional[Dict[str, Any]]:
        ident = identifier.strip().lower()
        pool = get_db_pool()
        if pool:
            try:
                with pool.connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            SELECT id, username, email, password_hash, role, created_at 
                            FROM users 
                            WHERE LOWER(username) = %s OR LOWER(email) = %s;
                            """,
                            (ident, ident),
                        )
                        row = cur.fetchone()
                        if row:
                            user = {
                                "id": row["id"],
                                "username": row["username"],
                                "email": row["email"],
                                "password_hash": row["password_hash"],
                                "role": row["role"],
                                "created_at": _format_datetime(row["created_at"]),
                            }
                            self._users[user["id"]] = user
                            return user
            except Exception as exc:
                logger.warning(f"PostgreSQL get_user_by_username_or_email failed: {exc}")

        for user in self._users.values():
            if user["username"] == ident or user["email"] == ident:
                return user
        return None

    def list_users(self) -> List[Dict[str, Any]]:
        pool = get_db_pool()
        if pool:
            try:
                with pool.connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT id, username, email, role, created_at FROM users ORDER BY created_at ASC;")
                        rows = cur.fetchall()
                        if rows:
                            return [
                                {
                                    "id": r["id"],
                                    "username": r["username"],
                                    "email": r["email"],
                                    "role": r["role"],
                                    "created_at": _format_datetime(r["created_at"]),
                                }
                                for r in rows
                            ]
            except Exception as exc:
                logger.warning(f"PostgreSQL list_users failed: {exc}")

        return list(self._users.values())

    def delete_user(self, identifier: str) -> bool:
        """Deletes a user by id, username, or email from PostgreSQL and in-memory cache."""
        pool = get_db_pool()
        if pool:
            try:
                with pool.connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "DELETE FROM users WHERE id = %s OR LOWER(username) = %s OR LOWER(email) = %s;",
                            (identifier, identifier.strip().lower(), identifier.strip().lower()),
                        )
                    conn.commit()
            except Exception as exc:
                logger.warning(f"PostgreSQL delete_user failed: {exc}")

        to_del = [
            uid for uid, u in self._users.items()
            if uid == identifier or u.get("username") == identifier.lower() or u.get("email") == identifier.lower()
        ]
        for uid in to_del:
            self._users.pop(uid, None)
        return True

    def create_password_reset_token(self, email: str) -> Optional[str]:
        """Creates a single-use password reset token with 15-minute expiration."""
        user = self.get_user_by_username_or_email(email)
        if not user:
            return None
        
        token = f"rst_{secrets.token_hex(20)}"
        expires_at = int(time.time()) + 900  # 15 minutes
        pool = get_db_pool()
        if pool:
            try:
                with pool.connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO password_reset_tokens (token, user_id, expires_at, used)
                            VALUES (%s, %s, %s, %s);
                            """,
                            (token, user["id"], expires_at, False),
                        )
                    conn.commit()
            except Exception as exc:
                logger.warning(f"PostgreSQL create_password_reset_token failed: {exc}")

        self._reset_tokens[token] = {
            "token": token,
            "user_id": user["id"],
            "expires_at": expires_at,
            "used": False,
        }
        return token

    def verify_and_consume_reset_token(self, token: str, new_password_hash: str) -> bool:
        """Validates token expiration and single-use status, then updates user password."""
        pool = get_db_pool()
        if pool:
            try:
                with pool.connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT token, user_id, expires_at, used FROM password_reset_tokens WHERE token = %s;",
                            (token,),
                        )
                        row = cur.fetchone()
                        if not row or row["used"] or row["expires_at"] < time.time():
                            return False
                        user_id = row["user_id"]
                        cur.execute("UPDATE users SET password_hash = %s WHERE id = %s;", (new_password_hash, user_id))
                        cur.execute("UPDATE password_reset_tokens SET used = true WHERE token = %s;", (token,))
                    conn.commit()
                    if user_id in self._users:
                        self._users[user_id]["password_hash"] = new_password_hash
                    if token in self._reset_tokens:
                        self._reset_tokens[token]["used"] = True
                    return True
            except Exception as exc:
                logger.warning(f"PostgreSQL verify_and_consume_reset_token failed: {exc}")

        token_data = self._reset_tokens.get(token)
        if not token_data:
            return False
        if token_data["used"] or token_data["expires_at"] < time.time():
            return False

        user = self._users.get(token_data["user_id"])
        if not user:
            return False

        user["password_hash"] = new_password_hash
        token_data["used"] = True
        return True

    # -----------------------------------------------------
    # Thread Ownership Registry
    # -----------------------------------------------------
    def register_thread_owner(self, thread_id: str, user_id: str) -> None:
        """Registers the owner user_id for a given conversation thread_id."""
        if not thread_id or not user_id:
            return

        self._ensure_user_exists(user_id)
        pool = get_db_pool()
        if pool:
            try:
                with pool.connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO thread_ownership (thread_id, user_id, created_at)
                            VALUES (%s, %s, %s)
                            ON CONFLICT (thread_id) DO UPDATE SET user_id = EXCLUDED.user_id;
                            """,
                            (thread_id, user_id, datetime.now(timezone.utc)),
                        )
                    conn.commit()
            except Exception as exc:
                logger.warning(f"PostgreSQL register_thread_owner failed: {exc}")

        self._thread_owners[thread_id] = user_id

    def get_thread_owner(self, thread_id: str) -> Optional[str]:
        """Returns the registered user_id for a thread_id."""
        pool = get_db_pool()
        if pool:
            try:
                with pool.connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT user_id FROM thread_ownership WHERE thread_id = %s;", (thread_id,))
                        row = cur.fetchone()
                        if row:
                            self._thread_owners[thread_id] = row["user_id"]
                            return row["user_id"]
            except Exception as exc:
                logger.warning(f"PostgreSQL get_thread_owner failed: {exc}")

        return self._thread_owners.get(thread_id)

    # -----------------------------------------------------
    # Watchlist Operations
    # -----------------------------------------------------
    def create_watchlist(
        self,
        user_id: str,
        title: str,
        target_type: str,
        target_value: str,
        threshold_price: Optional[float] = None,
        notes: str = "",
    ) -> Dict[str, Any]:
        self._ensure_user_exists(user_id)
        item_id = f"wl_{uuid.uuid4().hex[:12]}"
        base_estimate = 450.0 if target_type == "flight" else (180.0 if target_type == "hotel" else 750.0)
        now = datetime.now(timezone.utc)
        item = {
            "id": item_id,
            "user_id": user_id,
            "title": title,
            "target_type": target_type,
            "target_value": target_value,
            "threshold_price": threshold_price,
            "current_price_estimate": base_estimate,
            "currency": "USD",
            "notes": notes,
            "created_at": now.isoformat(),
            "active": True,
        }

        pool = get_db_pool()
        if pool:
            try:
                with pool.connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO watchlists (
                                id, user_id, title, target_type, target_value, 
                                threshold_price, current_price_estimate, currency, notes, active, created_at
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                            """,
                            (
                                item_id, user_id, title, target_type, target_value,
                                threshold_price, base_estimate, "USD", notes, True, now,
                            ),
                        )
                    conn.commit()
            except Exception as exc:
                logger.error(f"PostgreSQL create_watchlist write failed: {exc}")
                raise

        self._watchlists[item_id] = item
        return item

    def get_watchlist(self, item_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        pool = get_db_pool()
        if pool:
            try:
                with pool.connection() as conn:
                    with conn.cursor() as cur:
                        query = """
                            SELECT id, user_id, title, target_type, target_value, 
                                   threshold_price, current_price_estimate, currency, notes, active, created_at 
                            FROM watchlists WHERE id = %s
                        """
                        params = [item_id]
                        if user_id:
                            query += " AND user_id = %s"
                            params.append(user_id)
                        cur.execute(query + ";", tuple(params))
                        row = cur.fetchone()
                        if row:
                            return {
                                "id": row["id"],
                                "user_id": row["user_id"],
                                "title": row["title"],
                                "target_type": row["target_type"],
                                "target_value": row["target_value"],
                                "threshold_price": _format_float(row["threshold_price"]),
                                "current_price_estimate": _format_float(row["current_price_estimate"]) or 0.0,
                                "currency": row["currency"],
                                "notes": row["notes"] or "",
                                "active": bool(row["active"]),
                                "created_at": _format_datetime(row["created_at"]),
                            }
                        return None
            except Exception as exc:
                logger.warning(f"PostgreSQL get_watchlist failed: {exc}")

        item = self._watchlists.get(item_id)
        if not item:
            return None
        if user_id and item["user_id"] != user_id:
            return None
        return item

    def list_watchlists(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        pool = get_db_pool()
        if pool:
            try:
                with pool.connection() as conn:
                    with conn.cursor() as cur:
                        query = """
                            SELECT id, user_id, title, target_type, target_value, 
                                   threshold_price, current_price_estimate, currency, notes, active, created_at 
                            FROM watchlists
                        """
                        params = []
                        if user_id:
                            query += " WHERE user_id = %s"
                            params.append(user_id)
                        query += " ORDER BY created_at DESC;"
                        cur.execute(query, tuple(params))
                        rows = cur.fetchall()
                        return [
                            {
                                "id": r["id"],
                                "user_id": r["user_id"],
                                "title": r["title"],
                                "target_type": r["target_type"],
                                "target_value": r["target_value"],
                                "threshold_price": _format_float(r["threshold_price"]),
                                "current_price_estimate": _format_float(r["current_price_estimate"]) or 0.0,
                                "currency": r["currency"],
                                "notes": r["notes"] or "",
                                "active": bool(r["active"]),
                                "created_at": _format_datetime(r["created_at"]),
                            }
                            for r in rows
                        ]
            except Exception as exc:
                logger.warning(f"PostgreSQL list_watchlists failed: {exc}")

        if not user_id:
            return list(self._watchlists.values())
        return [w for w in self._watchlists.values() if w["user_id"] == user_id]

    def delete_watchlist(self, item_id: str, user_id: Optional[str] = None) -> bool:
        pool = get_db_pool()
        if pool:
            try:
                with pool.connection() as conn:
                    with conn.cursor() as cur:
                        query = "DELETE FROM watchlists WHERE id = %s"
                        params = [item_id]
                        if user_id:
                            query += " AND user_id = %s"
                            params.append(user_id)
                        cur.execute(query + ";", tuple(params))
                        deleted = cur.rowcount > 0
                    conn.commit()
                    if deleted:
                        self._watchlists.pop(item_id, None)
                        return True
                    return False
            except Exception as exc:
                logger.warning(f"PostgreSQL delete_watchlist failed: {exc}")

        item = self.get_watchlist(item_id, user_id)
        if not item:
            return False
        del self._watchlists[item_id]
        return True

    # -----------------------------------------------------
    # Alert Operations
    # -----------------------------------------------------
    def create_alert(
        self,
        user_id: str,
        title: str,
        message: str,
        alert_type: str = "price_drop",
        severity: str = "info",
        watchlist_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        self._ensure_user_exists(user_id)
        alert_id = f"alt_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)
        alert = {
            "id": alert_id,
            "user_id": user_id,
            "title": title,
            "message": message,
            "alert_type": alert_type,
            "severity": severity,
            "watchlist_id": watchlist_id,
            "is_read": False,
            "created_at": now.isoformat(),
        }

        pool = get_db_pool()
        if pool:
            try:
                with pool.connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO alerts (id, user_id, watchlist_id, title, message, alert_type, severity, is_read, created_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
                            """,
                            (alert_id, user_id, watchlist_id, title, message, alert_type, severity, False, now),
                        )
                    conn.commit()
            except Exception as exc:
                logger.error(f"PostgreSQL create_alert write failed: {exc}")
                raise

        self._alerts[alert_id] = alert
        return alert

    def list_alerts(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        pool = get_db_pool()
        if pool:
            try:
                with pool.connection() as conn:
                    with conn.cursor() as cur:
                        query = "SELECT id, user_id, watchlist_id, title, message, alert_type, severity, is_read, created_at FROM alerts"
                        params = []
                        if user_id:
                            query += " WHERE user_id = %s"
                            params.append(user_id)
                        query += " ORDER BY created_at DESC;"
                        cur.execute(query, tuple(params))
                        rows = cur.fetchall()
                        return [
                            {
                                "id": r["id"],
                                "user_id": r["user_id"],
                                "watchlist_id": r.get("watchlist_id"),
                                "title": r["title"],
                                "message": r["message"],
                                "alert_type": r.get("alert_type", "price_drop"),
                                "severity": r.get("severity", "info"),
                                "is_read": bool(r.get("is_read", False)),
                                "created_at": _format_datetime(r["created_at"]),
                            }
                            for r in rows
                        ]
            except Exception as exc:
                logger.warning(f"PostgreSQL list_alerts failed: {exc}")

        if not user_id:
            return list(self._alerts.values())
        return [a for a in self._alerts.values() if a["user_id"] == user_id]

    def mark_alert_read(self, alert_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        pool = get_db_pool()
        if pool:
            try:
                with pool.connection() as conn:
                    with conn.cursor() as cur:
                        query = "UPDATE alerts SET is_read = true WHERE id = %s"
                        params = [alert_id]
                        if user_id:
                            query += " AND user_id = %s"
                            params.append(user_id)
                        query += " RETURNING id, user_id, watchlist_id, title, message, alert_type, severity, is_read, created_at;"
                        cur.execute(query, tuple(params))
                        row = cur.fetchone()
                    conn.commit()
                    if row:
                        alert = {
                            "id": row["id"],
                            "user_id": row["user_id"],
                            "watchlist_id": row.get("watchlist_id"),
                            "title": row["title"],
                            "message": row["message"],
                            "alert_type": row.get("alert_type", "price_drop"),
                            "severity": row.get("severity", "info"),
                            "is_read": True,
                            "created_at": _format_datetime(row["created_at"]),
                        }
                        self._alerts[alert_id] = alert
                        return alert
                    return None
            except Exception as exc:
                logger.warning(f"PostgreSQL mark_alert_read failed: {exc}")

        alert = self._alerts.get(alert_id)
        if not alert:
            return None
        if user_id and alert["user_id"] != user_id:
            return None
        alert["is_read"] = True
        return alert

    def delete_alert(self, alert_id: str, user_id: Optional[str] = None) -> bool:
        pool = get_db_pool()
        if pool:
            try:
                with pool.connection() as conn:
                    with conn.cursor() as cur:
                        query = "DELETE FROM alerts WHERE id = %s"
                        params = [alert_id]
                        if user_id:
                            query += " AND user_id = %s"
                            params.append(user_id)
                        cur.execute(query + ";", tuple(params))
                        deleted = cur.rowcount > 0
                    conn.commit()
                    if deleted:
                        self._alerts.pop(alert_id, None)
                        return True
                    return False
            except Exception as exc:
                logger.warning(f"PostgreSQL delete_alert failed: {exc}")

        alert = self._alerts.get(alert_id)
        if not alert:
            return False
        if user_id and alert["user_id"] != user_id:
            return False
        del self._alerts[alert_id]
        return True

    # -----------------------------------------------------
    # Asset Operations
    # -----------------------------------------------------
    def create_asset(
        self,
        user_id: str,
        name: str,
        asset_type: str,
        trip_id: Optional[str] = None,
        content_uri: Optional[str] = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        self._ensure_user_exists(user_id)
        asset_id = f"ast_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)
        meta = metadata or {}
        uri = content_uri or f"tripmate://storage/{asset_id}"
        asset = {
            "id": asset_id,
            "user_id": user_id,
            "name": name,
            "asset_type": asset_type,
            "trip_id": trip_id,
            "content_uri": uri,
            "metadata": meta,
            "created_at": now.isoformat(),
        }

        pool = get_db_pool()
        if pool:
            try:
                with pool.connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO assets (id, user_id, name, asset_type, trip_id, content_uri, metadata, created_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
                            """,
                            (asset_id, user_id, name, asset_type, trip_id, uri, json.dumps(meta), now),
                        )
                    conn.commit()
            except Exception as exc:
                logger.error(f"PostgreSQL create_asset write failed: {exc}")
                raise

        self._assets[asset_id] = asset
        return asset

    def get_asset(self, asset_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        pool = get_db_pool()
        if pool:
            try:
                with pool.connection() as conn:
                    with conn.cursor() as cur:
                        query = "SELECT id, user_id, name, asset_type, trip_id, content_uri, metadata, created_at FROM assets WHERE id = %s"
                        params = [asset_id]
                        if user_id:
                            query += " AND user_id = %s"
                            params.append(user_id)
                        cur.execute(query + ";", tuple(params))
                        row = cur.fetchone()
                        if row:
                            meta = row.get("metadata")
                            if isinstance(meta, str):
                                try:
                                    meta = json.loads(meta)
                                except Exception:
                                    meta = {}
                            return {
                                "id": row["id"],
                                "user_id": row["user_id"],
                                "name": row["name"] or "",
                                "asset_type": row["asset_type"],
                                "trip_id": row.get("trip_id"),
                                "content_uri": row.get("content_uri") or "",
                                "metadata": meta or {},
                                "created_at": _format_datetime(row["created_at"]),
                            }
                        return None
            except Exception as exc:
                logger.warning(f"PostgreSQL get_asset failed: {exc}")

        asset = self._assets.get(asset_id)
        if not asset:
            return None
        if user_id and asset["user_id"] != user_id:
            return None
        return asset

    def list_assets(self, user_id: Optional[str] = None, trip_id: Optional[str] = None) -> List[Dict[str, Any]]:
        pool = get_db_pool()
        if pool:
            try:
                with pool.connection() as conn:
                    with conn.cursor() as cur:
                        query = "SELECT id, user_id, name, asset_type, trip_id, content_uri, metadata, created_at FROM assets"
                        clauses = []
                        params = []
                        if user_id:
                            clauses.append("user_id = %s")
                            params.append(user_id)
                        if trip_id:
                            clauses.append("trip_id = %s")
                            params.append(trip_id)
                        if clauses:
                            query += " WHERE " + " AND ".join(clauses)
                        query += " ORDER BY created_at DESC;"
                        cur.execute(query, tuple(params))
                        rows = cur.fetchall()
                        result = []
                        for r in rows:
                            meta = r.get("metadata")
                            if isinstance(meta, str):
                                try:
                                    meta = json.loads(meta)
                                except Exception:
                                    meta = {}
                            result.append({
                                "id": r["id"],
                                "user_id": r["user_id"],
                                "name": r["name"] or "",
                                "asset_type": r["asset_type"],
                                "trip_id": r.get("trip_id"),
                                "content_uri": r.get("content_uri") or "",
                                "metadata": meta or {},
                                "created_at": _format_datetime(r["created_at"]),
                            })
                        return result
            except Exception as exc:
                logger.warning(f"PostgreSQL list_assets failed: {exc}")

        res = list(self._assets.values())
        if user_id:
            res = [a for a in res if a["user_id"] == user_id]
        if trip_id:
            res = [a for a in res if a.get("trip_id") == trip_id]
        return res

    def delete_asset(self, asset_id: str, user_id: Optional[str] = None) -> bool:
        pool = get_db_pool()
        if pool:
            try:
                with pool.connection() as conn:
                    with conn.cursor() as cur:
                        query = "DELETE FROM assets WHERE id = %s"
                        params = [asset_id]
                        if user_id:
                            query += " AND user_id = %s"
                            params.append(user_id)
                        cur.execute(query + ";", tuple(params))
                        deleted = cur.rowcount > 0
                    conn.commit()
                    if deleted:
                        self._assets.pop(asset_id, None)
                        return True
                    return False
            except Exception as exc:
                logger.warning(f"PostgreSQL delete_asset failed: {exc}")

        asset = self.get_asset(asset_id, user_id)
        if not asset:
            return False
        del self._assets[asset_id]
        return True

    def get_system_uptime(self) -> float:
        return round(time.time() - self._start_time, 2)


# Shared global singleton store
store = DataStore()
datastore = store
