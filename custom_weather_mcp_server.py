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

import requests
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# Initialize FastMCP Server instance
mcp = FastMCP("Weather MCP Server")

OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
REQUEST_TIMEOUT_SECONDS = 20


def _get_api_key() -> str:
    """Validates presence of OpenWeather API key."""
    if not OPENWEATHER_API_KEY:
        raise RuntimeError(
            "OPENWEATHER_API_KEY is missing from the project .env file."
        )
    return OPENWEATHER_API_KEY


def _request_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    """Sends HTTP GET request to OpenWeather API and returns JSON response."""
    try:
        response = requests.get(
            url,
            params=params,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        details = ""
        failed_response = getattr(exc, "response", None)
        if failed_response is not None:
            details = f" Response: {failed_response.text[:500]}"
        raise RuntimeError(f"OpenWeather request failed: {exc}.{details}") from exc


@mcp.tool()
def get_current_weather(city: str) -> dict[str, Any]:
    """MCP Tool: Return current weather metrics for a destination city."""
    city = city.strip()
    if not city:
        raise ValueError("city cannot be empty")

    data = _request_json(
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
def get_forecast(city: str) -> dict[str, Any]:
    """MCP Tool: Return the first five 3-hour forecast entries for a destination city."""
    city = city.strip()
    if not city:
        raise ValueError("city cannot be empty")

    data = _request_json(
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