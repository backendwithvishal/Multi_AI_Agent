"""
Adapter Pattern Module

Normalizes external integrations and MCP tools into unified application interfaces.
"""

from tripmate.adapters.weather_adapter import WeatherServiceAdapter, NormalizedWeatherData
from tripmate.adapters.flight_adapter import FlightServiceAdapter, NormalizedFlightOffer
from tripmate.adapters.tavily_adapter import TavilySearchAdapter, NormalizedSearchCitation

__all__ = [
    "WeatherServiceAdapter",
    "NormalizedWeatherData",
    "FlightServiceAdapter",
    "NormalizedFlightOffer",
    "TavilySearchAdapter",
    "NormalizedSearchCitation",
]
