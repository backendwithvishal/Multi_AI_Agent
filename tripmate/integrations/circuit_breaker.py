"""
Circuit Breaker Resilience Pattern

This module prevents cascade failures when calling third-party MCP APIs:
- CLOSED: Everything works normally. Requests pass through.
- OPEN: Too many failures occurred (>= threshold). Fast-fails requests immediately without calling the external service.
- HALF_OPEN: Cooldown period expired. Sends a trial request to test if the external service has recovered.
"""

import asyncio
import time
from enum import Enum
from typing import Any, Callable, Dict


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreakerOpenException(Exception):
    """Raised when attempting a call while the circuit breaker is OPEN."""
    pass


class CircuitBreaker:
    """Manages failure counters and cooldown state for external service calls."""

    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        cooldown_seconds: float = 30.0,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0
        self._lock = asyncio.Lock()

    async def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Executes an async function guarded by circuit breaker state logic."""
        async with self._lock:
            now = time.time()
            if self.state == CircuitState.OPEN:
                # If cooldown period has elapsed, move to HALF_OPEN to test service recovery
                if now - self.last_failure_time > self.cooldown_seconds:
                    self.state = CircuitState.HALF_OPEN
                else:
                    raise CircuitBreakerOpenException(
                        f"CircuitBreaker '{self.name}' is OPEN. Call rejected to protect downstream service."
                    )

        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
        except Exception as exc:
            async with self._lock:
                self.failure_count += 1
                self.last_failure_time = time.time()
                if self.failure_count >= self.failure_threshold:
                    self.state = CircuitState.OPEN
            raise exc

        # On successful execution, reset circuit to CLOSED state
        async with self._lock:
            if self.state in (CircuitState.HALF_OPEN, CircuitState.OPEN):
                self.state = CircuitState.CLOSED
                self.failure_count = 0
        return result

    def get_status(self) -> Dict[str, Any]:
        """Returns diagnostic telemetry for the circuit breaker."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "last_failure_time": self.last_failure_time,
        }
