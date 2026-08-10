"""
Model Router Abstraction Module

This module provides a unified LLM routing interface to instantiate and direct requests to:
- Fast models for guardrails and fast classification (Groq / OpenRouter)
- Reasoning models for dynamic planning, synthesis, and critic evaluations
- Primary provider: Groq (`GROQ_API_KEY`)
- Fallback provider: OpenRouter (`OPENROUTER_API_KEY`)
"""

import os
from enum import Enum
from pathlib import Path
from typing import Any, Optional
from dotenv import load_dotenv

from tripmate.config.settings import settings

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class ModelTier(str, Enum):
    FAST = "fast"
    REASONING = "reasoning"
    SPECIALIZED = "specialized"


class ModelRouter:
    """Manages LLM provider routing for Groq and OpenRouter tiers."""

    @property
    def groq_api_key(self) -> Optional[str]:
        return (settings.GROQ_API_KEY or os.getenv("GROQ_API_KEY") or "").strip() or None

    @property
    def openrouter_api_key(self) -> Optional[str]:
        return (settings.OPENROUTER_API_KEY or os.getenv("OPENROUTER_API_KEY") or "").strip() or None

    def has_active_provider(self) -> bool:
        """Returns True if at least one LLM provider key is configured."""
        return bool(self.groq_api_key or self.openrouter_api_key)

    def get_active_provider_name(self) -> Optional[str]:
        """Returns the identifier of the primary active LLM provider."""
        if self.groq_api_key:
            return "groq"
        if self.openrouter_api_key:
            return "openrouter"
        return None

    def get_model(self, tier: ModelTier = ModelTier.REASONING) -> Optional[Any]:
        """Returns an initialized LLM instance for specified performance tier with dynamic fallback."""
        # Refresh environment settings in case .env was updated at runtime
        load_dotenv(BASE_DIR / ".env", override=False)

        groq_key = self.groq_api_key
        openrouter_key = self.openrouter_api_key

        if not groq_key and not openrouter_key:
            return None

        # 1. Primary Provider: Groq API
        if groq_key:
            model_name = "llama-3.3-70b-versatile"
            if tier == ModelTier.FAST:
                model_name = os.getenv("FAST_LLM_MODEL", "llama-3.1-8b-instant")
            elif tier == ModelTier.REASONING:
                model_name = os.getenv("REASONING_LLM_MODEL", "llama-3.3-70b-versatile")

            try:
                from langchain_groq import ChatGroq
                return ChatGroq(
                    model=model_name,
                    api_key=groq_key,
                    timeout=settings.LLM_TIMEOUT_SECONDS,
                )
            except Exception as exc:
                print(f"ModelRouter Groq initialization notice: {exc}")

        # 2. Fallback Provider: OpenRouter API
        if openrouter_key:
            if tier == ModelTier.FAST:
                openrouter_model = os.getenv(
                    "OPENROUTER_FAST_MODEL",
                    os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.1-8b-instruct"),
                )
            else:
                openrouter_model = os.getenv(
                    "OPENROUTER_REASONING_MODEL",
                    os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct"),
                )

            try:
                from langchain_groq import ChatGroq
                return ChatOpenAI(
                    model=openrouter_model,
                    api_key=openrouter_key,
                    base_url="https://openrouter.ai/api/v1",
                    timeout=settings.LLM_TIMEOUT_SECONDS,
                )
            except ImportError:
                try:
                    from langchain_community.chat_models import ChatOpenAI
                    return ChatOpenAI(
                        model_name=openrouter_model,
                        openai_api_key=openrouter_key,
                        openai_api_base="https://openrouter.ai/api/v1",
                        request_timeout=settings.LLM_TIMEOUT_SECONDS,
                    )
                except Exception as exc:
                    print(f"ModelRouter OpenRouter initialization notice: {exc}")
            except Exception as exc:
                print(f"ModelRouter OpenRouter initialization notice: {exc}")

        return None


# Shared singleton router instance
model_router = ModelRouter()

