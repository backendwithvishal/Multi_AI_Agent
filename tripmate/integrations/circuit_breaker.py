"""
Circuit Breaker Resilience Pattern

Protects the application from cascade failures when calling third-party APIs
(MCP Servers, Tavily Search, AviationStack, OpenWeather, Amadeus GDS, and LLMs).

State Machine:
- CLOSED: Normal operation. All requests pass through. Transient errors increment failure count.
- OPEN: Failure threshold exceeded (>= failure_threshold). Requests fast-fail immediately
  with CircuitBreakerOpenException without invoking the remote dependency.
- HALF_OPEN: Cooldown period expired. A limited number of trial requests are admitted
  to probe dependency health. Consecutive successes reset the circuit to CLOSED. Any trial failure
  immediately trips the circuit back to OPEN.

Transient vs Permanent Failure Discrimination:
- Permanent errors (e.g. ValueError, TypeError, KeyError, 4xx Bad Request/Unauthorized)
  do NOT increment the circuit failure counter because retrying or waiting will not fix them.
- Transient errors (e.g. ConnectionError, TimeoutError, asyncio.TimeoutError, 5xx Server Errors,
  rate limits, RuntimeError) increment the failure counter.

Process Boundaries:
In Python, this circuit breaker is process-local. Each worker process tracks its own
dependency health counters.
"""

import asyncio
import logging
import time
from enum import Enum
from typing import Any, Callable, Dict, Optional, Set, Tuple, Type

from tripmate.core.singleton import SingletonMeta

logger = logging.getLogger("tripmate.circuit_breaker")


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreakerOpenException(Exception):
    """Raised when attempting a call while the circuit breaker is OPEN or trial capacity is saturated."""

    def __init__(self, message: str, breaker_name: str = "", retry_after_seconds: float = 0.0):
        super().__init__(message)
        self.breaker_name = breaker_name
        self.retry_after_seconds = retry_after_seconds


# Exceptions that represent bugs, bad user inputs, or permanent authorization failures
DEFAULT_PERMANENT_EXCEPTIONS: Tuple[Type[BaseException], ...] = (
    ValueError,
    TypeError,
    KeyError,
    IndexError,
    AttributeError,
    AssertionError,
)


class CircuitBreaker:
    """
    Enterprise Circuit Breaker managing health states, trial concurrency,
    and failure discrimination for external services.
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        cooldown_seconds: float = 30.0,
        success_threshold: int = 1,
        half_open_max_trials: int = 1,
        permanent_exceptions: Optional[Tuple[Type[BaseException], ...]] = None,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.success_threshold = success_threshold
        self.half_open_max_trials = half_open_max_trials
        self.permanent_exceptions = permanent_exceptions or DEFAULT_PERMANENT_EXCEPTIONS

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.consecutive_successes = 0
        self.active_half_open_trials = 0
        self.last_failure_time = 0.0
        self.last_state_change = time.time()
        self._lock = asyncio.Lock()

    def is_transient_error(self, exc: BaseException) -> bool:
        """
        Determines if an exception is transient (network/timeout/server error)
        or permanent (input/validation/logic error).
        """
        if isinstance(exc, self.permanent_exceptions):
            return False
        return True

    async def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Executes an async or sync callable guarded by circuit breaker state logic."""
        async with self._lock:
            now = time.time()
            if self.state == CircuitState.OPEN:
                elapsed = now - self.last_failure_time
                if elapsed > self.cooldown_seconds:
                    logger.info(
                        f"[CIRCUIT BREAKER] '{self.name}' cooldown elapsed ({elapsed:.1f}s > {self.cooldown_seconds}s). Transitioning OPEN -> HALF_OPEN"
                    )
                    self.state = CircuitState.HALF_OPEN
                    self.active_half_open_trials = 0
                    self.consecutive_successes = 0
                    self.last_state_change = now
                else:
                    retry_after = round(self.cooldown_seconds - elapsed, 2)
                    raise CircuitBreakerOpenException(
                        f"CircuitBreaker '{self.name}' is OPEN. Call rejected to protect downstream service. Retry after {retry_after}s.",
                        breaker_name=self.name,
                        retry_after_seconds=retry_after,
                    )

            if self.state == CircuitState.HALF_OPEN:
                if self.active_half_open_trials >= self.half_open_max_trials:
                    raise CircuitBreakerOpenException(
                        f"CircuitBreaker '{self.name}' is HALF_OPEN and trial capacity is saturated ({self.active_half_open_trials}/{self.half_open_max_trials}). Call rejected.",
                        breaker_name=self.name,
                    )
                self.active_half_open_trials += 1

        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
        except Exception as exc:
            async with self._lock:
                if self.state == CircuitState.HALF_OPEN:
                    self.active_half_open_trials = max(0, self.active_half_open_trials - 1)

                # Discriminate permanent vs transient failure
                if self.is_transient_error(exc):
                    self.failure_count += 1
                    self.last_failure_time = time.time()
                    self.consecutive_successes = 0

                    if self.state == CircuitState.HALF_OPEN or self.failure_count >= self.failure_threshold:
                        prev_state = self.state
                        self.state = CircuitState.OPEN
                        self.last_state_change = time.time()
                        logger.warning(
                            f"[CIRCUIT BREAKER] '{self.name}' tripped {prev_state.value} -> OPEN (failures={self.failure_count}/{self.failure_threshold}, error={exc})"
                        )
                else:
                    logger.debug(
                        f"[CIRCUIT BREAKER] '{self.name}' permanent exception ignored ({type(exc).__name__}): {exc}"
                    )
            raise exc

        # On success
        async with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                self.active_half_open_trials = max(0, self.active_half_open_trials - 1)
                self.consecutive_successes += 1
                if self.consecutive_successes >= self.success_threshold:
                    logger.info(
                        f"[CIRCUIT BREAKER] '{self.name}' trial succeeded ({self.consecutive_successes}/{self.success_threshold}). Transitioning HALF_OPEN -> CLOSED"
                    )
                    self.state = CircuitState.CLOSED
                    self.failure_count = 0
                    self.consecutive_successes = 0
                    self.last_state_change = time.time()
            elif self.state == CircuitState.OPEN:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.consecutive_successes = 0
                self.last_state_change = time.time()
            else:
                # In CLOSED state, decay or reset transient failure counter on clean success
                if self.failure_count > 0:
                    self.failure_count = max(0, self.failure_count - 1)

        return result

    def reset(self) -> None:
        """Manually resets circuit breaker to CLOSED state and clears failure counters."""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.consecutive_successes = 0
        self.active_half_open_trials = 0
        self.last_failure_time = 0.0
        self.last_state_change = time.time()
        logger.info(f"[CIRCUIT BREAKER] '{self.name}' manually reset to CLOSED.")

    def get_status(self) -> Dict[str, Any]:
        """Returns diagnostic telemetry for the circuit breaker."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "failure_threshold": self.failure_threshold,
            "cooldown_seconds": self.cooldown_seconds,
            "last_failure_time": self.last_failure_time,
            "consecutive_successes": self.consecutive_successes,
            "last_state_change": self.last_state_change,
        }


class CircuitBreakerRegistry(metaclass=SingletonMeta):
    """
    Thread-safe registry for managing all named circuit breakers across the platform.
    """

    def __init__(self):
        self._breakers: Dict[str, CircuitBreaker] = {}

    def register(self, breaker: CircuitBreaker) -> CircuitBreaker:
        self._breakers[breaker.name] = breaker
        return breaker

    def get(self, name: str) -> Optional[CircuitBreaker]:
        return self._breakers.get(name)

    def get_all(self) -> Dict[str, CircuitBreaker]:
        return self._breakers.copy()

    def get_all_status(self) -> Dict[str, Any]:
        return {name: b.get_status() for name, b in self._breakers.items()}

    def reset_all(self) -> None:
        for breaker in self._breakers.values():
            breaker.reset()


circuit_breaker_registry = CircuitBreakerRegistry()
