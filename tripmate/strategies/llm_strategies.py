"""
LLM Provider Strategy Pattern

Defines strategy contracts and concrete provider strategies for Groq, OpenRouter,
and Hugging Face model execution, decoupling provider selection from routing logic.
"""

import os
from abc import ABC, abstractmethod
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


def create_openai_compatible_client(model_name: str, api_key: str, base_url: str, timeout: float) -> Any:
    """Helper creating an OpenAI-compatible REST API client for OpenRouter and Hugging Face."""
    try:
        from langchain_groq import ChatGroq
        return ChatGroq(
            model=model_name,
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
        )
    except Exception:
        pass

    try:
        from langchain_community.chat_models import ChatOpenAI
        return ChatOpenAI(
            model_name=model_name,
            openai_api_key=api_key,
            openai_api_base=base_url,
            request_timeout=timeout,
        )
    except Exception as exc:
        print(f"OpenAI-compatible client creation notice: {exc}")
        return None


class LLMProviderStrategy(ABC):
    """Abstract Strategy interface for an LLM provider."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Unique provider identifier (e.g. 'groq', 'openrouter', 'huggingface')."""
        pass

    @property
    @abstractmethod
    def priority(self) -> int:
        """Priority rank (lower numbers evaluated first in fallback chain)."""
        pass

    @abstractmethod
    def is_configured(self) -> bool:
        """Returns True if the required API keys or credentials are present."""
        pass

    @abstractmethod
    def create_model(self, tier: ModelTier, timeout: float) -> Optional[Any]:
        """Instantiates and returns the provider chat model client for the requested tier."""
        pass


class GroqProviderStrategy(LLMProviderStrategy):
    """Primary LLM Strategy using Groq hardware acceleration."""

    @property
    def provider_name(self) -> str:
        return "groq"

    @property
    def priority(self) -> int:
        return 1

    @property
    def api_key(self) -> Optional[str]:
        return (settings.GROQ_API_KEY or os.getenv("GROQ_API_KEY") or "").strip() or None

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def create_model(self, tier: ModelTier, timeout: float) -> Optional[Any]:
        api_key = self.api_key
        if not api_key:
            return None

        model_name = "llama-3.3-70b-versatile"
        if tier == ModelTier.FAST:
            model_name = os.getenv("FAST_LLM_MODEL", "llama-3.1-8b-instant")
        elif tier == ModelTier.REASONING:
            model_name = os.getenv("REASONING_LLM_MODEL", "llama-3.3-70b-versatile")

        try:
            from langchain_groq import ChatGroq
            return ChatGroq(
                model=model_name,
                api_key=api_key,
                timeout=timeout,
            )
        except Exception as exc:
            print(f"GroqProviderStrategy initialization notice: {exc}")
            return None


class OpenRouterProviderStrategy(LLMProviderStrategy):
    """Secondary LLM Strategy using OpenRouter multi-model gateway."""

    @property
    def provider_name(self) -> str:
        return "openrouter"

    @property
    def priority(self) -> int:
        return 2

    @property
    def api_key(self) -> Optional[str]:
        return (settings.OPENROUTER_API_KEY or os.getenv("OPENROUTER_API_KEY") or "").strip() or None

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def create_model(self, tier: ModelTier, timeout: float) -> Optional[Any]:
        api_key = self.api_key
        if not api_key:
            return None

        if tier == ModelTier.FAST:
            openrouter_model = os.getenv(
                "OPENROUTER_FAST_MODEL",
                os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.1-8b-instruct:free"),
            )
        else:
            openrouter_model = os.getenv(
                "OPENROUTER_REASONING_MODEL",
                os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free"),
            )

        try:
            return create_openai_compatible_client(
                model_name=openrouter_model,
                api_key=api_key,
                base_url="https://openrouter.ai/api/v1",
                timeout=timeout,
            )
        except Exception as exc:
            print(f"OpenRouterProviderStrategy initialization notice: {exc}")
            return None


class HuggingFaceProviderStrategy(LLMProviderStrategy):
    """Tertiary LLM Strategy using Hugging Face Serverless Inference API."""

    @property
    def provider_name(self) -> str:
        return "huggingface"

    @property
    def priority(self) -> int:
        return 3

    @property
    def api_key(self) -> Optional[str]:
        return (
            settings.HUGGINGFACE_API_KEY
            or os.getenv("HUGGINGFACE_API_KEY")
            or os.getenv("HUGGING_FACE_API_KEY")
            or ""
        ).strip() or None

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def create_model(self, tier: ModelTier, timeout: float) -> Optional[Any]:
        api_key = self.api_key
        if not api_key:
            return None

        if tier == ModelTier.FAST:
            hf_model = os.getenv("HUGGINGFACE_FAST_MODEL", "meta-llama/Meta-Llama-3-8B-Instruct")
        else:
            hf_model = os.getenv(
                "HUGGINGFACE_REASONING_MODEL",
                os.getenv("HUGGINGFACE_MODEL", "meta-llama/Llama-3.3-70B-Instruct"),
            )

        try:
            return create_openai_compatible_client(
                model_name=hf_model,
                api_key=api_key,
                base_url="https://router.huggingface.co/v1",
                timeout=timeout,
            )
        except Exception as exc:
            print(f"HuggingFaceProviderStrategy initialization notice: {exc}")
            return None
