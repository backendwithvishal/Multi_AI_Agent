"""
Weather Service Adapter Pattern

Adapts raw OpenWeather MCP responses into standardized domain schemas and evidence metadata.
"""

from typing import Any, Dict, Optional
from pydantic import BaseModel
from tripmate.schemas.agents import EvidenceItem, EvidenceType, VerificationStatus


class NormalizedWeatherData(BaseModel):
    """Application-facing normalized weather representation."""
    city: str
    summary: str
    current_weather: str
    forecast: str
    is_live: bool = True


class WeatherServiceAdapter:
    """Normalizes disparate OpenWeather MCP formats into domain objects and evidence items."""

    @classmethod
    def adapt_weather_response(cls, city: str, raw_output: str) -> NormalizedWeatherData:
        """Parses and normalizes raw weather search text into a clean model."""
        cleaned = raw_output.strip() if raw_output else ""
        is_live = not ("unavailable" in cleaned.lower() or "seasonal advice" in cleaned.lower())

        current_part = cleaned
        forecast_part = ""

        if "Forecast:" in cleaned:
            parts = cleaned.split("Forecast:", 1)
            current_part = parts[0].replace("Current Weather:", "").strip()
            forecast_part = parts[1].strip()

        return NormalizedWeatherData(
            city=city,
            summary=cleaned[:300],
            current_weather=current_part or "Clear conditions",
            forecast=forecast_part or "Seasonal forecast",
            is_live=is_live,
        )

    @classmethod
    def create_evidence_item(cls, weather_data: NormalizedWeatherData) -> EvidenceItem:
        """Constructs an audited provenance EvidenceItem from normalized weather data."""
        if weather_data.is_live:
            return EvidenceItem(
                source_name="OpenWeather MCP",
                source_type=EvidenceType.API,
                status=VerificationStatus.VERIFIED,
                confidence=0.95,
                details=f"Live meteorological conditions for {weather_data.city}",
            )
        return EvidenceItem(
            source_name="Seasonal Weather Fallback",
            source_type=EvidenceType.FALLBACK,
            status=VerificationStatus.UNCERTAIN,
            confidence=0.55,
            details=f"Historical seasonal forecast for {weather_data.city}",
        )
