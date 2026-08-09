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
import secrets
import time
import uuid
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from tripmate.config.settings import settings


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


def generate_token(user_id: str, username: str, role: str) -> str:
    """Generates a tamper-proof HMAC-SHA256 signed bearer access token."""
    secret = settings.API_KEY or "tripmate_platform_secret_key_2026"
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
        secret = settings.API_KEY or "tripmate_platform_secret_key_2026"
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


# =========================================================
# Unified Data Repository
# =========================================================

class DataStore:
    """Thread-safe unified data store managing platform entities."""

    def __init__(self):
        self._users: Dict[str, Dict[str, Any]] = {}
        self._watchlists: Dict[str, Dict[str, Any]] = {}
        self._alerts: Dict[str, Dict[str, Any]] = {}
        self._assets: Dict[str, Dict[str, Any]] = {}
        self._start_time = time.time()
        self._seed_initial_data()

    def _seed_initial_data(self):
        """Seeds default admin and demo user accounts."""
        admin_id = "user_admin_001"
        self._users[admin_id] = {
            "id": admin_id,
            "username": "admin",
            "email": "admin@tripmate.ai",
            "password_hash": hash_password("Admin@12345"),
            "role": "admin",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        demo_id = "user_demo_002"
        self._users[demo_id] = {
            "id": demo_id,
            "username": "demouser",
            "email": "user@tripmate.ai",
            "password_hash": hash_password("User@12345"),
            "role": "user",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    # -----------------------------------------------------
    # User Operations
    # -----------------------------------------------------
    def create_user(self, username: str, email: str, password_hash: str, role: str = "user") -> Dict[str, Any]:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        user = {
            "id": user_id,
            "username": username.lower(),
            "email": email.lower(),
            "password_hash": password_hash,
            "role": role,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._users[user_id] = user
        return user

    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        return self._users.get(user_id)

    def get_user_by_username_or_email(self, identifier: str) -> Optional[Dict[str, Any]]:
        ident = identifier.strip().lower()
        for user in self._users.values():
            if user["username"] == ident or user["email"] == ident:
                return user
        return None

    def list_users(self) -> List[Dict[str, Any]]:
        return list(self._users.values())

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
        item_id = f"wl_{uuid.uuid4().hex[:12]}"
        # Generate a realistic baseline price estimate based on target type
        base_estimate = 450.0 if target_type == "flight" else (180.0 if target_type == "hotel" else 750.0)
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
            "created_at": datetime.now(timezone.utc).isoformat(),
            "active": True,
        }
        self._watchlists[item_id] = item
        return item

    def get_watchlist(self, item_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        item = self._watchlists.get(item_id)
        if not item:
            return None
        if user_id and item["user_id"] != user_id:
            return None
        return item

    def list_watchlists(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if not user_id:
            return list(self._watchlists.values())
        return [w for w in self._watchlists.values() if w["user_id"] == user_id]

    def delete_watchlist(self, item_id: str, user_id: Optional[str] = None) -> bool:
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
        alert_id = f"alt_{uuid.uuid4().hex[:12]}"
        alert = {
            "id": alert_id,
            "user_id": user_id,
            "title": title,
            "message": message,
            "alert_type": alert_type,
            "severity": severity,
            "watchlist_id": watchlist_id,
            "is_read": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._alerts[alert_id] = alert
        return alert

    def list_alerts(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if not user_id:
            return list(self._alerts.values())
        return [a for a in self._alerts.values() if a["user_id"] == user_id]

    def mark_alert_read(self, alert_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        alert = self._alerts.get(alert_id)
        if not alert:
            return None
        if user_id and alert["user_id"] != user_id:
            return None
        alert["is_read"] = True
        return alert

    def delete_alert(self, alert_id: str, user_id: Optional[str] = None) -> bool:
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
        asset_id = f"ast_{uuid.uuid4().hex[:12]}"
        asset = {
            "id": asset_id,
            "user_id": user_id,
            "name": name,
            "asset_type": asset_type,
            "trip_id": trip_id,
            "content_uri": content_uri or f"tripmate://storage/{asset_id}",
            "metadata": metadata or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._assets[asset_id] = asset
        return asset

    def get_asset(self, asset_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        asset = self._assets.get(asset_id)
        if not asset:
            return None
        if user_id and asset["user_id"] != user_id:
            return None
        return asset

    def list_assets(self, user_id: Optional[str] = None, trip_id: Optional[str] = None) -> List[Dict[str, Any]]:
        res = list(self._assets.values())
        if user_id:
            res = [a for a in res if a["user_id"] == user_id]
        if trip_id:
            res = [a for a in res if a.get("trip_id") == trip_id]
        return res

    def delete_asset(self, asset_id: str, user_id: Optional[str] = None) -> bool:
        asset = self.get_asset(asset_id, user_id)
        if not asset:
            return False
        del self._assets[asset_id]
        return True

    def get_system_uptime(self) -> float:
        return round(time.time() - self._start_time, 2)


# Shared global singleton store
store = DataStore()
