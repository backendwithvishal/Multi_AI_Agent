"""
Custom FastMCP Weather Server

This file runs an independent stdio Model Context Protocol (MCP) server for OpenWeather:
1. `get_current_weather`: Queries OpenWeather API for current temperature, humidity, and condition.
2. `get_forecast`: Queries OpenWeather API for short-term forecast details.

Launched as a stdio subprocess by `mcp_client.py`.
"""

import os
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# Initialize FastMCP Server instance
mcp = FastMCP("Weather MCP Server")

OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
REQUEST_TIMEOUT_SECONDS = 10.0


def _get_api_key() -> str:
    """Validates presence of OpenWeather API key."""
    key = os.getenv("OPENWEATHER_API_KEY")
    if not key or not key.strip():
        raise RuntimeError(
            "OPENWEATHER_API_KEY is missing from the project .env file."
        )
    return key.strip()


from urllib.parse import urlparse

ALLOWED_WEATHER_HOSTS = ["api.openweathermap.org"]
MAX_WEATHER_RESPONSE_BYTES = 50_000


async def _request_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    """Sends async non-blocking HTTP GET request to OpenWeather API with SSRF protection."""
    parsed = urlparse(url)
    if parsed.hostname not in ALLOWED_WEATHER_HOSTS:
        raise ValueError(f"SSRF Protection: Host '{parsed.hostname}' is not in allowed weather hosts.")

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            if len(response.content) > MAX_WEATHER_RESPONSE_BYTES:
                raise ValueError(f"Response size exceeded {MAX_WEATHER_RESPONSE_BYTES} bytes limit.")
            return response.json()
    except httpx.HTTPStatusError as exc:
        details = f" Response: {exc.response.text[:500]}"
        raise RuntimeError(f"OpenWeather request failed with status {exc.response.status_code}.{details}") from exc
    except httpx.RequestError as exc:
        raise RuntimeError(f"OpenWeather network request failed: {exc}") from exc


@mcp.tool()
async def get_current_weather(city: str) -> dict[str, Any]:
    """MCP Tool: Return current weather metrics for a destination city."""
    city = city.strip()
    if not city:
        raise ValueError("city cannot be empty")

    data = await _request_json(
        "https://api.openweathermap.org/data/2.5/weather",
        {
            "q": city,
            "appid": _get_api_key(),
            "units": "metric",
        },
    )

    return {
        "city": data["name"],
        "temperature_c": data["main"]["temp"],
        "feels_like_c": data["main"]["feels_like"],
        "humidity": data["main"]["humidity"],
        "condition": data["weather"][0]["description"],
        "wind_speed": data["wind"]["speed"],
    }


@mcp.tool()
async def get_forecast(city: str) -> dict[str, Any]:
    """MCP Tool: Return the first five 3-hour forecast entries for a destination city."""
    city = city.strip()
    if not city:
        raise ValueError("city cannot be empty")

    data = await _request_json(
        "https://api.openweathermap.org/data/2.5/forecast",
        {
            "q": city,
            "appid": _get_api_key(),
            "units": "metric",
        },
    )

    forecast = [
        {
            "datetime": item["dt_txt"],
            "temperature_c": item["main"]["temp"],
            "condition": item["weather"][0]["description"],
        }
        for item in data.get("list", [])[:5]
    ]

    return {
        "city": data.get("city", {}).get("name", city),
        "forecast": forecast,
    }

if __name__ == "__main__":
    # Run server on standard I/O (stdio) transport
    mcp.run(transport="stdio")