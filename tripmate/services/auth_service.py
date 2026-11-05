"""
Authentication & User Management Service

Handles registration, credential validation, token issuance, and user profiles.
"""

import secrets
from typing import Any, Dict, Optional

from tripmate.config.settings import settings
from tripmate.database.store import generate_token, hash_password, verify_password, store
from tripmate.schemas import TokenResponse, UserLoginRequest, UserProfile, UserRegisterRequest


class AuthService:
    """Authentication and identity service."""

    def __init__(self, data_store=None):
        self._store = data_store or store

    def register_user(
        self,
        req: UserRegisterRequest,
        admin_secret: Optional[str] = None,
        is_caller_admin: bool = False,
    ) -> Dict[str, Any]:
        """Registers a new user account safely."""
        existing = self._store.get_user_by_username_or_email(req.username)
        if existing:
            raise ValueError(f"Username '{req.username}' is already registered.")

        existing_email = self._store.get_user_by_username_or_email(req.email)
        if existing_email:
            raise ValueError(f"Email '{req.email}' is already registered.")

        # Prevent unauthorized self-assignment of administrative roles
        assigned_role = "user"
        if req.role == "admin":
            if is_caller_admin:
                assigned_role = "admin"
            elif (
                settings.ADMIN_REGISTRATION_SECRET
                and admin_secret
                and secrets.compare_digest(admin_secret.strip(), settings.ADMIN_REGISTRATION_SECRET)
            ):
                assigned_role = "admin"

        hashed_pw = hash_password(req.password)
        user = self._store.create_user(
            username=req.username,
            email=req.email,
            password_hash=hashed_pw,
            role=assigned_role,
        )
        token = generate_token(user["id"], user["username"], user["role"])
        return {
            "access_token": token,
            "token_type": "bearer",
            "user_id": user["id"],
            "username": user["username"],
            "role": user["role"],
        }

    def authenticate_user(self, req: UserLoginRequest) -> Dict[str, Any]:
        """Authenticates user credentials and returns an access token."""
        user = self._store.get_user_by_username_or_email(req.username_or_email)
        if not user or not verify_password(req.password, user["password_hash"]):
            raise ValueError("Invalid username/email or password.")

        token = generate_token(user["id"], user["username"], user["role"])
        return {
            "access_token": token,
            "token_type": "bearer",
            "user_id": user["id"],
            "username": user["username"],
            "role": user["role"],
        }

    def request_password_reset(self, email: str) -> Dict[str, Any]:
        """Generates a secure password reset token without leaking account existence."""
        reset_token = self._store.create_password_reset_token(email)
        res: Dict[str, Any] = {
            "message": "If an account matches that email address, password reset instructions have been dispatched.",
        }
        if not settings.is_production:
            res["reset_token"] = reset_token
        return res

    def reset_password(self, reset_token: str, new_password: str) -> bool:
        """Validates token and updates user account password."""
        hashed_pw = hash_password(new_password)
        success = self._store.verify_and_consume_reset_token(reset_token, hashed_pw)
        if not success:
            raise ValueError("Invalid, expired, or already consumed reset token.")
        return True

    def get_profile(self, user_id: str) -> Optional[UserProfile]:
        """Fetches user profile by user ID."""
        user = self._store.get_user_by_id(user_id)
        if not user:
            return None
        return UserProfile(
            id=user["id"],
            username=user["username"],
            email=user["email"],
            role=user["role"],
            created_at=user["created_at"],
        )


auth_service = AuthService()
