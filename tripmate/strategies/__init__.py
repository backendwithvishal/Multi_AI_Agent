"""
Strategy Pattern Module

Exposes interchangeable provider and search strategies.
"""

from tripmate.strategies.llm_strategies import (
    GroqProviderStrategy,
    HuggingFaceProviderStrategy,
    LLMProviderStrategy,
    ModelTier,
    OpenRouterProviderStrategy,
)
from tripmate.strategies.booking_strategies import (
    AmadeusSandboxFlightStrategy,
    AmadeusSandboxHotelStrategy,
    IFlightSearchStrategy,
    IHotelSearchStrategy,
)

__all__ = [
    "ModelTier",
    "LLMProviderStrategy",
    "GroqProviderStrategy",
    "OpenRouterProviderStrategy",
    "HuggingFaceProviderStrategy",
    "IFlightSearchStrategy",
    "IHotelSearchStrategy",
    "AmadeusSandboxFlightStrategy",
    "AmadeusSandboxHotelStrategy",
]
