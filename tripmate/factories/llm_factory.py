"""
LLM Client Factory Pattern

Centralizes the creation and validation of language model provider clients.
Validates configurations and fails with descriptive error messages when unsupported
providers or missing credentials are requested.
"""

from typing import Any, Dict, Optional, Type
from tripmate.strategies.llm_strategies import (
    GroqProviderStrategy,
    HuggingFaceProviderStrategy,
    LLMProviderStrategy,
    ModelTier,
    OpenRouterProviderStrategy,
)


class LLMClientFactory:
    """
    Factory for instantiating validated LLM clients across supported providers.
    """

    _strategies: Dict[str, LLMProviderStrategy] = {
        "groq": GroqProviderStrategy(),
        "openrouter": OpenRouterProviderStrategy(),
        "huggingface": HuggingFaceProviderStrategy(),
    }

    @classmethod
    def register_strategy(cls, strategy: LLMProviderStrategy) -> None:
        """Registers a new provider strategy with the factory."""
        cls._strategies[strategy.provider_name.lower()] = strategy

    @classmethod
    def create_client(
        cls,
        provider: str,
        tier: ModelTier = ModelTier.REASONING,
        timeout: float = 60.0,
    ) -> Any:
        """
        Creates an LLM client instance for the given provider name and model tier.
        Raises ValueError if the provider is unsupported or unconfigured.
        """
        normalized_provider = provider.strip().lower()
        strategy = cls._strategies.get(normalized_provider)
        if not strategy:
            available = list(cls._strategies.keys())
            raise ValueError(
                f"Unsupported LLM provider '{provider}'. Available providers: {available}"
            )

        if not strategy.is_configured():
            raise ValueError(
                f"LLM provider '{provider}' is not configured. Please supply the required API key in your environment or .env file."
            )

        client = strategy.create_model(tier=tier, timeout=timeout)
        if client is None:
            raise RuntimeError(
                f"Failed to initialize client for provider '{provider}' and tier '{tier.value}'."
            )
        return client

    @classmethod
    def get_supported_providers(cls) -> Dict[str, bool]:
        """Returns map of supported providers and their active configuration status."""
        return {name: strat.is_configured() for name, strat in cls._strategies.items()}
