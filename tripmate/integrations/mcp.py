"""
Resilient MCP Tool Wrappers

This module wraps all raw Model Context Protocol (MCP) calls with circuit breakers and timeouts:
- `safe_tavily_search`: Searches for hotel/destination data using Tavily MCP.
- `safe_aviation_call`: Queries flight/airline data using AviationStack MCP.
- `safe_weather_search`: Fetches weather and forecast data using OpenWeather MCP.
- `safe_extract_destination`: Extracts destination city name from prompt using LLM.

If an external service is slow or down, these wrappers return graceful fallback messages instead of failing the workflow.
"""

import asyncio
from typing import Any, Dict
from mcp_client import (
    tavily_mcp_search as raw_tavily_mcp_search,
    aviation_mcp_call as raw_aviation_mcp_call,
    weather_mcp_search as raw_weather_mcp_search,
    forecast_mcp_search as raw_forecast_mcp_search,
    extract_destination as raw_extract_destination,
)
from tripmate.integrations.circuit_breaker import CircuitBreaker, CircuitBreakerOpenException
from tripmate.config.settings import settings

# Dedicated Circuit Breakers for third-party services
tavily_breaker = CircuitBreaker("tavily_api", failure_threshold=3, cooldown_seconds=30.0)
aviation_breaker = CircuitBreaker("aviationstack_api", failure_threshold=3, cooldown_seconds=30.0)
weather_breaker = CircuitBreaker("openweather_api", failure_threshold=3, cooldown_seconds=30.0)


async def safe_tavily_search(query: str) -> str:
    """Safe Tavily Search wrapper with timeout and circuit breaker protection."""
    try:
        return await asyncio.wait_for(
            tavily_breaker.call(raw_tavily_mcp_search, query),
            timeout=settings.EXTERNAL_API_TIMEOUT_SECONDS,
        )
    except (CircuitBreakerOpenException, asyncio.TimeoutError, Exception) as exc:
        print(f"Resilient Tavily Search fallback used: {exc}")
        return "Live web hotel search is temporarily unavailable. Providing standard destination advice."


async def safe_aviation_call(tool_name: str, tool_args: Dict[str, Any] | None = None) -> Any:
    """Safe AviationStack call wrapper with timeout and circuit breaker protection."""
    try:
        return await asyncio.wait_for(
            aviation_breaker.call(raw_aviation_mcp_call, tool_name, tool_args),
            timeout=settings.EXTERNAL_API_TIMEOUT_SECONDS,
        )
    except (CircuitBreakerOpenException, asyncio.TimeoutError, Exception) as exc:
        print(f"Resilient AviationStack call fallback used: {exc}")
        return f"Live flight status data unavailable: {exc}"


async def safe_weather_search(city: str) -> str:
    """Safe OpenWeather call wrapper fetching both current weather and forecast."""
    try:
        current_data = await asyncio.wait_for(
            weather_breaker.call(raw_weather_mcp_search, city),
            timeout=settings.EXTERNAL_API_TIMEOUT_SECONDS,
        )
        forecast_data = await asyncio.wait_for(
            weather_breaker.call(raw_forecast_mcp_search, city),
            timeout=settings.EXTERNAL_API_TIMEOUT_SECONDS,
        )
        return f"Current Weather:\n{current_data}\n\nForecast:\n{forecast_data}"
    except (CircuitBreakerOpenException, asyncio.TimeoutError, Exception) as exc:
        print(f"Resilient Weather Search fallback used: {exc}")
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
