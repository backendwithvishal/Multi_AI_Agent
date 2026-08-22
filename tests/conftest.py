import gc
import pytest
from tripmate.middleware import SlidingWindowRateLimiter


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
