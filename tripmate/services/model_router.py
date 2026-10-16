"""
Model Router Abstraction Module (Refactored with Strategy & Singleton Patterns)

This module provides a unified LLM routing interface to instantiate and direct requests to:
- Fast models for guardrails and fast classification (Groq / OpenRouter)
- Reasoning models for dynamic planning, synthesis, and critic evaluations
- Primary provider strategy: Groq (`GROQ_API_KEY`)
- Secondary provider strategy: OpenRouter (`OPENROUTER_API_KEY`)
- Tertiary provider strategy: Hugging Face (`HUGGINGFACE_API_KEY`)
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv

from tripmate.config.settings import settings
from tripmate.core.singleton import SingletonMeta
from tripmate.strategies.llm_strategies import (
    GroqProviderStrategy,
    HuggingFaceProviderStrategy,
    LLMProviderStrategy,
    ModelTier,
    OpenRouterProviderStrategy,
    create_openai_compatible_client,
)

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Re-export for backward compatibility
_create_openai_compatible_client = create_openai_compatible_client


class ModelRouter(metaclass=SingletonMeta):
    """
    Manages LLM provider routing with fallback across Groq, OpenRouter, and Hugging Face.
    Implemented as a thread-safe Singleton using Strategy Pattern for provider execution.
    """

    def __init__(self, strategies: Optional[List[LLMProviderStrategy]] = None):
        if strategies is not None:
            self._strategies = list(strategies)
        else:
            self._strategies = [
                GroqProviderStrategy(),
                OpenRouterProviderStrategy(),
                HuggingFaceProviderStrategy(),
            ]

    def register_strategy(self, strategy: LLMProviderStrategy) -> None:
        """Registers an additional or custom provider strategy."""
        self._strategies.append(strategy)
        self._strategies.sort(key=lambda s: s.priority)

    @property
    def groq_api_key(self) -> Optional[str]:
        return (settings.GROQ_API_KEY or os.getenv("GROQ_API_KEY") or "").strip() or None

    @property
    def openrouter_api_key(self) -> Optional[str]:
        return (settings.OPENROUTER_API_KEY or os.getenv("OPENROUTER_API_KEY") or "").strip() or None

    @property
    def huggingface_api_key(self) -> Optional[str]:
        return (
            settings.HUGGINGFACE_API_KEY
            or os.getenv("HUGGINGFACE_API_KEY")
            or os.getenv("HUGGING_FACE_API_KEY")
            or ""
        ).strip() or None

    def has_active_provider(self) -> bool:
        """Returns True if at least one LLM provider key is configured."""
        return any(strat.is_configured() for strat in self._strategies)

    def get_active_provider_name(self) -> Optional[str]:
        """Returns the identifier of the highest-priority active LLM provider."""
        sorted_strats = sorted(self._strategies, key=lambda s: s.priority)
        for strat in sorted_strats:
            if strat.is_configured():
                return strat.provider_name
        return None

    def get_model(self, tier: ModelTier = ModelTier.REASONING) -> Optional[Any]:
        """
        Returns an initialized LLM instance with dynamic fallback across provider strategies.
        """
        load_dotenv(BASE_DIR / ".env", override=False)

        sorted_strats = sorted(self._strategies, key=lambda s: s.priority)
        for strat in sorted_strats:
            if strat.is_configured():
                client = strat.create_model(tier=tier, timeout=settings.LLM_TIMEOUT_SECONDS)
                if client is not None:
                    return client

        return None


# Shared singleton router instance
model_router = ModelRouter()