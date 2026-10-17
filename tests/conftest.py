import gc
import pytest
from tripmate.middleware import SlidingWindowRateLimiter
from tripmate.database.store import store


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Autouse fixture to reset sliding window rate limiter state before each test."""
    for obj in gc.get_objects():
        if isinstance(obj, SlidingWindowRateLimiter):
            obj._requests.clear()
    yield
    for obj in gc.get_objects():
        if isinstance(obj, SlidingWindowRateLimiter):
            obj._requests.clear()


@pytest.fixture(autouse=True)
def clean_ephemeral_test_users():
    """Cleans up ephemeral test users created during previous test runs to ensure idempotency."""
    test_usernames = [
        "recovery_user",
        "super_adm",
        "sub_admin",
        "traveler_jane",
        "regular_user_tom",
        "admin_super",
    ]
    for username in test_usernames:
        store.delete_user(username)
    yield
    for username in test_usernames:
        store.delete_user(username)
