"""
Authentication, Password Recovery, HITL State & Resource Ownership Test Suite
"""

import pytest
from httpx import AsyncClient, ASGITransport
from app import app
from tripmate.config.settings import settings


@pytest.mark.asyncio
async def test_password_recovery_flow():
    """Tests 2-step single-use password recovery flow."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Register user
        reg = await client.post(
            "/api/v1/auth/register",
            json={
                "username": "recovery_user",
                "email": "recovery@example.com",
                "password": "OldPassword123!",
                "role": "user",
            },
        )
        assert reg.status_code == 200

        # Request reset token
        forgot_resp = await client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "recovery@example.com"},
        )
        assert forgot_resp.status_code == 200
        reset_token = forgot_resp.json()["data"]["reset_token"]
        assert reset_token is not None

        # Reset password
        reset_resp = await client.post(
            "/api/v1/auth/reset-password",
            json={
                "reset_token": reset_token,
                "new_password": "NewSecurePassword456!",
            },
        )
        assert reset_resp.status_code == 200

        # Verify old password fails
        login_fail = await client.post(
            "/api/v1/auth/login",
            json={"username_or_email": "recovery_user", "password": "OldPassword123!"},
        )
        assert login_fail.status_code == 401

        # Verify new password succeeds
        login_success = await client.post(
            "/api/v1/auth/login",
            json={"username_or_email": "recovery_user", "password": "NewSecurePassword456!"},
        )
        assert login_success.status_code == 200


@pytest.mark.asyncio
async def test_hitl_approval_nonexistent_thread():
    """Tests 404 response when attempting to approve a non-existent thread."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/travel/approve",
            json={
                "thread_id": "non_existent_thread_999",
                "approved": True,
                "feedback": "Great trip!",
            },
        )
        assert resp.status_code == 404
        data = resp.json()
        assert data["success"] is False
        assert data["error"]["code"] == "THREAD_NOT_FOUND"


@pytest.mark.asyncio
async def test_financial_authentication_enforcement(monkeypatch):
    """Tests authentication requirement on financial calculation endpoints."""
    monkeypatch.setattr(settings, "AUTH_REQUIRED", True)
    monkeypatch.setattr(settings, "API_KEY", "secret_key_123")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Without auth -> 401
        unauth_resp = await client.post(
            "/api/v1/financial/calculate",
            json={"flight_estimate": 500, "hotel_nightly_rate": 100, "nights": 3},
        )
        assert unauth_resp.status_code == 401

        # With auth -> 200
        auth_resp = await client.post(
            "/api/v1/financial/calculate",
            json={"flight_estimate": 500, "hotel_nightly_rate": 100, "nights": 3},
            headers={"Authorization": "Bearer secret_key_123"},
        )
        assert auth_resp.status_code == 200
        assert auth_resp.json()["data"]["grand_total"] > 0


@pytest.mark.asyncio
async def test_admin_user_provisioning(monkeypatch):
    """Tests POST /api/v1/admin/users endpoint for admin provisioning and error handling."""
    monkeypatch.setattr(settings, "ADMIN_REGISTRATION_SECRET", "master_admin_secret")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Register initial admin using secret header
        admin_reg = await client.post(
            "/api/v1/auth/register",
            json={
                "username": "super_adm",
                "email": "super_adm@tripmate.ai",
                "password": "MasterAdminPass123!",
                "role": "admin",
            },
            headers={"X-Admin-Secret": "master_admin_secret"},
        )
        assert admin_reg.status_code == 200
        admin_token = admin_reg.json()["data"]["access_token"]

        # Admin provisions a new admin user
        prov_resp = await client.post(
            "/api/v1/admin/users",
            json={
                "username": "sub_admin",
                "email": "subadmin@tripmate.ai",
                "password": "SubAdminPass123!",
                "role": "admin",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert prov_resp.status_code == 200
        assert prov_resp.json()["data"]["role"] == "admin"

        # Duplicate username -> 400 with USER_CREATION_FAILED
        dup_resp = await client.post(
            "/api/v1/admin/users",
            json={
                "username": "sub_admin",
                "email": "subadmin2@tripmate.ai",
                "password": "SubAdminPass123!",
                "role": "admin",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert dup_resp.status_code == 400
        assert dup_resp.json()["error"]["code"] == "USER_CREATION_FAILED"
