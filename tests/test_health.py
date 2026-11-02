import pytest
from unittest.mock import patch
from fastapi import Response
from app import health_live, health_ready, hybrid_cache


def run_coro(coro):
    """Executes a coroutine and its awaited child coroutines synchronously to completion."""
    stack = [coro]
    val = None
    exc = None
    while stack:
        top = stack[-1]
        try:
            if exc is not None:
                to_send = top.throw(exc)
                exc = None
            else:
                to_send = top.send(val)
            val = None
            if hasattr(to_send, "__await__"):
                stack.append(to_send.__await__())
            elif hasattr(to_send, "send"):
                stack.append(to_send)
        except StopIteration as e:
            stack.pop()
            val = e.value
            exc = None
        except Exception as e:
            stack.pop()
            exc = e
            val = None
    if exc is not None:
        raise exc
    return val


def async_ret(val):
    async def _inner(*args, **kwargs):
        return val
    return _inner


def test_health_live_endpoint():
    """Liveness probe: verifies process is alive and returns 200 without secrets."""
    res = run_coro(health_live())
    assert res.get("status") in ("ok", "alive")
    for secret_pattern in ["password", "secret", "gsk_", "postgres_pass", "token"]:
        assert secret_pattern not in str(res).lower()


def test_health_ready_when_all_healthy():
    """Readiness probe: 200 when Postgres and Redis are up."""
    with patch("app.check_db_health", return_value={"status": "healthy"}), \
         patch.object(hybrid_cache, "ping", side_effect=async_ret(True)):
        resp = Response()
        data = run_coro(health_ready(resp))
        assert resp.status_code == 200
        assert data.get("status") == "ready"
        assert data.get("services", {}).get("database") == "healthy"
        assert data.get("services", {}).get("redis") == "healthy"


def test_health_ready_503_when_postgres_unhealthy():
    """Readiness probe: 503 when Postgres is down."""
    with patch("app.check_db_health", return_value={"status": "unhealthy", "error": "Connection refused"}), \
         patch.object(hybrid_cache, "ping", side_effect=async_ret(True)):
        resp = Response()
        data = run_coro(health_ready(resp))
        assert resp.status_code == 503
        assert data.get("status") == "unhealthy"
        assert data.get("services", {}).get("database") == "unhealthy"


def test_health_ready_503_when_redis_unhealthy():
    """Readiness probe: 503 when Redis is down."""
    with patch("app.check_db_health", return_value={"status": "healthy"}), \
         patch.object(hybrid_cache, "ping", side_effect=async_ret(False)):
        resp = Response()
        data = run_coro(health_ready(resp))
        assert resp.status_code == 503
        assert data.get("status") == "unhealthy"
        assert data.get("services", {}).get("redis") == "unhealthy"


def test_health_ready_response_has_no_secrets():
    """Readiness probe response must never leak database URLs, passwords, or keys."""
    with patch("app.check_db_health", return_value={"status": "unhealthy", "error": "db_err"}), \
         patch.object(hybrid_cache, "ping", side_effect=async_ret(False)):
        resp = Response()
        data = run_coro(health_ready(resp))
        text = str(data).lower()
        for forbidden in ["postgres_pass", "password", "postgresql://", "redis://", "gsk_", "secret_key"]:
            assert forbidden not in text
