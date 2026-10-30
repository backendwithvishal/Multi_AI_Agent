"""
Resilient MCP Tool Wrappers with Circuit Breakers, Exponential Backoff Jitter, and Redis Caching
"""

import asyncio
import logging
import random
from typing import Any, Callable, Dict, Optional
from mcp_client import (
    tavily_mcp_search as raw_tavily_mcp_search,
    aviation_mcp_call as raw_aviation_mcp_call,
    weather_mcp_search as raw_weather_mcp_search,
    forecast_mcp_search as raw_forecast_mcp_search,
    extract_destination as raw_extract_destination,
)
from tripmate.integrations.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenException,
    circuit_breaker_registry,
)
from tripmate.config.settings import settings
from tripmate.cache.redis_cache import hybrid_cache

logger = logging.getLogger("tripmate.mcp")

# Register third-party service circuit breakers in the central registry
tavily_breaker = circuit_breaker_registry.register(
    CircuitBreaker("tavily_api", failure_threshold=3, cooldown_seconds=30.0)
)
aviation_breaker = circuit_breaker_registry.register(
    CircuitBreaker("aviationstack_api", failure_threshold=3, cooldown_seconds=30.0)
)
weather_breaker = circuit_breaker_registry.register(
    CircuitBreaker("openweather_api", failure_threshold=3, cooldown_seconds=30.0)
)


async def execute_with_backoff_and_jitter(
    coro_func: Callable[[], Any],
    max_retries: int = 2,
    base_delay: float = 0.4,
    max_delay: float = 2.5,
) -> Any:
    """Executes an async callable with bounded exponential backoff and randomized jitter."""
    for attempt in range(max_retries + 1):
        try:
            return await coro_func()
        except (CircuitBreakerOpenException, asyncio.CancelledError):
            raise
        except Exception as exc:
            if attempt >= max_retries:
                raise
            delay = min(max_delay, base_delay * (2**attempt))
            jitter = random.uniform(0.85, 1.15)
            sleep_time = delay * jitter
            logger.info(
                f"[MCP Retry] Attempt {attempt + 1}/{max_retries} failed ({exc}). Retrying in {sleep_time:.2f}s..."
            )
            await asyncio.sleep(sleep_time)


def _cap_tool_response(output: Any) -> Any:
    """Caps external tool output to configured maximum byte limit."""
    if isinstance(output, str) and len(output.encode("utf-8")) > settings.MAX_TOOL_OUTPUT_BYTES:
        return output[: settings.MAX_TOOL_OUTPUT_BYTES] + "\n...[truncated tool output]"
    return output


async def safe_tavily_search(query: str, user_id: Optional[str] = None) -> str:
    """Safe Tavily Search with Redis caching, exponential backoff, timeout, and circuit breaker."""
    async def _fetch():
        async def _call():
            return await asyncio.wait_for(
                tavily_breaker.call(raw_tavily_mcp_search, query),
                timeout=settings.EXTERNAL_API_TIMEOUT_SECONDS,
            )

        raw_res = await execute_with_backoff_and_jitter(_call, max_retries=1)
        return str(_cap_tool_response(raw_res))

    try:
        return await hybrid_cache.get_or_set_mcp(
            namespace="tavily_hotel",
            query_data=query,
            coro_func=_fetch,
            user_id=user_id,
            ttl_seconds=settings.MCP_CACHE_TTL_SECONDS,
        )
    except (CircuitBreakerOpenException, asyncio.TimeoutError, Exception) as exc:
        logger.warning(f"Resilient Tavily Search fallback used: {exc}")
        return "Live web hotel search is temporarily unavailable. Providing standard destination advice."


async def safe_aviation_call(
    tool_name: str,
    tool_args: Dict[str, Any] | None = None,
    user_id: Optional[str] = None,
) -> Any:
    """Safe AviationStack call with Redis caching, retry, timeout, and circuit breaker."""
    async def _fetch():
        async def _call():
            return await asyncio.wait_for(
                aviation_breaker.call(raw_aviation_mcp_call, tool_name, tool_args),
                timeout=settings.EXTERNAL_API_TIMEOUT_SECONDS,
            )

        raw_res = await execute_with_backoff_and_jitter(_call, max_retries=1)
        return _cap_tool_response(raw_res)

    cache_key_data = {"tool": tool_name, "args": tool_args or {}}
    try:
        return await hybrid_cache.get_or_set_mcp(
            namespace="aviation_call",
            query_data=cache_key_data,
            coro_func=_fetch,
            user_id=user_id,
            ttl_seconds=settings.MCP_CACHE_TTL_SECONDS,
        )
    except (CircuitBreakerOpenException, asyncio.TimeoutError, Exception) as exc:
        logger.warning(f"Resilient AviationStack call fallback used: {exc}")
        return f"Live flight status data unavailable: {exc}"


async def safe_weather_search(city: str, user_id: Optional[str] = None) -> str:
    """Safe OpenWeather call with Redis caching, timeout, and circuit breaker protection."""
    async def _fetch():
        async def _call_current():
            return await asyncio.wait_for(
                weather_breaker.call(raw_weather_mcp_search, city),
                timeout=settings.EXTERNAL_API_TIMEOUT_SECONDS,
            )

        async def _call_forecast():
            return await asyncio.wait_for(
                weather_breaker.call(raw_forecast_mcp_search, city),
                timeout=settings.EXTERNAL_API_TIMEOUT_SECONDS,
            )

        current_data = await execute_with_backoff_and_jitter(_call_current, max_retries=1)
        forecast_data = await execute_with_backoff_and_jitter(_call_forecast, max_retries=1)
        full_res = f"Current Weather:\n{current_data}\n\nForecast:\n{forecast_data}"
        return str(_cap_tool_response(full_res))

    try:
        return await hybrid_cache.get_or_set_mcp(
            namespace="weather_search",
            query_data=city,
            coro_func=_fetch,
            user_id=user_id,
            ttl_seconds=settings.MCP_CACHE_TTL_SECONDS,
        )
    except (CircuitBreakerOpenException, asyncio.TimeoutError, Exception) as exc:
        logger.warning(f"Resilient Weather Search fallback used: {exc}")
        return f"Live weather forecast for {city} is unavailable. Providing general seasonal advice."


async def safe_extract_destination(query: str) -> str:
    """Helper to extract target destination city string using LLM with fallback."""
    try:
        return await asyncio.wait_for(
            raw_extract_destination(query),
            timeout=settings.LLM_TIMEOUT_SECONDS,
        )
    except Exception:
        return "Destination"
