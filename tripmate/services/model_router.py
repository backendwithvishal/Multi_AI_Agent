"""
Model Router Abstraction Module

This module provides a unified LLM routing interface to instantiate and direct requests to:
- Fast models for guardrails and fast classification (Groq / OpenRouter)
- Reasoning models for dynamic planning, synthesis, and critic evaluations
- Primary provider: Groq (`GROQ_API_KEY`)
- Secondary provider: OpenRouter (`OPENROUTER_API_KEY`)
- Tertiary provider: Hugging Face (`HUGGINGFACE_API_KEY`)
"""

import os
from enum import Enum
from pathlib import Path
from typing import Any, Optional
from dotenv import load_dotenv

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, AIMessage
from langchain_core.outputs import ChatResult, ChatGeneration

from tripmate.config.settings import settings

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class ModelTier(str, Enum):
    FAST = "fast"
    REASONING = "reasoning"
    SPECIALIZED = "specialized"


def _create_openai_compatible_client(model_name: str, api_key: str, base_url: str, timeout: float) -> Any:
    """
    Helper creating an OpenAI-compatible REST API client for OpenRouter and Hugging Face.
    Supports GROQ_API_KEY, OPENROUTER_API_KEY, and HUGGINGFACE_API_KEY.
    """
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


class ModelRouter:
    """Manages LLM provider routing with fallback across Groq, OpenRouter, and Hugging Face."""

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
        return bool(self.groq_api_key or self.openrouter_api_key or self.huggingface_api_key)

    def get_active_provider_name(self) -> Optional[str]:
        """Returns the identifier of the primary active LLM provider."""
        if self.groq_api_key:
            return "groq"
        if self.openrouter_api_key:
            return "openrouter"
        if self.huggingface_api_key:
            return "huggingface"
        return None

    def get_model(self, tier: ModelTier = ModelTier.REASONING) -> Optional[Any]:
        """Returns an initialized LLM instance with dynamic fallback across providers."""
        # Refresh environment settings in case .env was updated at runtime
        load_dotenv(BASE_DIR / ".env", override=False)

        groq_key = self.groq_api_key
        openrouter_key = self.openrouter_api_key
        hf_key = self.huggingface_api_key

        if not groq_key and not openrouter_key and not hf_key:
            return None

        # 1. Primary Provider: Groq API (using GROQ_API_KEY)
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

        # 2. Secondary Provider: OpenRouter API (using OPENROUTER_API_KEY)
        if openrouter_key:
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
                client = _create_openai_compatible_client(
                    model_name=openrouter_model,
                    api_key=openrouter_key,
                    base_url="https://openrouter.ai/api/v1",
                    timeout=settings.LLM_TIMEOUT_SECONDS,
                )
                if client:
                    return client
            except Exception as exc:
                print(f"ModelRouter OpenRouter initialization notice: {exc}")

        # 3. Tertiary Provider: Hugging Face API (using HUGGINGFACE_API_KEY)
        if hf_key:
            if tier == ModelTier.FAST:
                hf_model = os.getenv("HUGGINGFACE_FAST_MODEL", "meta-llama/Meta-Llama-3-8B-Instruct")
            else:
                hf_model = os.getenv(
                    "HUGGINGFACE_REASONING_MODEL",
                    os.getenv("HUGGINGFACE_MODEL", "meta-llama/Llama-3.3-70B-Instruct"),
                )

            try:
                client = _create_openai_compatible_client(
                    model_name=hf_model,
                    api_key=hf_key,
                    base_url="https://router.huggingface.co/v1",
                    timeout=settings.LLM_TIMEOUT_SECONDS,
                )
                if client:
                    return client
            except Exception as exc:
                print(f"ModelRouter Hugging Face initialization notice: {exc}")

        return None


# Shared singleton router instance
model_router = ModelRouter()