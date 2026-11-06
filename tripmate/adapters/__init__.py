"""
Adapter Pattern Module

Normalizes external integrations and MCP tools into unified application interfaces.
"""

from tripmate.adapters.flight_adapter import FlightServiceAdapter, NormalizedFlightOffer
from tripmate.adapters.tavily_adapter import (
    NormalizedSearchCitation,
    TavilySearchAdapter,
)
from tripmate.adapters.weather_adapter import (
    NormalizedWeatherData,
    WeatherServiceAdapter,
)

__all__ = [
    "WeatherServiceAdapter",
    "NormalizedWeatherData",
    "FlightServiceAdapter",
    "NormalizedFlightOffer",
    "TavilySearchAdapter",
    "NormalizedSearchCitation",
]
