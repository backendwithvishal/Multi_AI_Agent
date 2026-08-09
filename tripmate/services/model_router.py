"""
Model Router Abstraction Module

This module provides a unified LLM routing interface to instantiate and direct requests to:
- Fast models for guardrail classifications & destination extraction
- Reasoning models for dynamic planning, synthesis, and critic evaluations
- Multiple provider backends (Groq, OpenRouter / OpenAI compatible)
"""

import os
from enum import Enum
from typing import Any, Optional
from tripmate.config.settings import settings


class ModelTier(str, Enum):
    FAST = "fast"
    REASONING = "reasoning"
    SPECIALIZED = "specialized"


class ModelRouter:
    """Manages multi-provider LLM selection and model tier routing."""

    def __init__(self):
        self.groq_api_key = settings.GROQ_API_KEY
        self.openrouter_api_key = settings.OPENROUTER_API_KEY

    def get_model(self, tier: ModelTier = ModelTier.REASONING) -> Optional[Any]:
        """Returns initialized LLM instance for specified performance tier."""
        if not self.groq_api_key and not self.openrouter_api_key:
            return None

        model_name = "llama-3.3-70b-versatile"
        if tier == ModelTier.FAST:
            model_name = os.getenv("FAST_LLM_MODEL", "llama-3.1-8b-instant")
        elif tier == ModelTier.REASONING:
            model_name = os.getenv("REASONING_LLM_MODEL", "llama-3.3-70b-versatile")

        # Try LangChain Groq provider first if key present
        if self.groq_api_key:
            try:
                from langchain_groq import ChatGroq
                return ChatGroq(
                    model=model_name,
                    api_key=self.groq_api_key,
                    timeout=settings.LLM_TIMEOUT_SECONDS,
                )
            except Exception as exc:
                print(f"ModelRouter ChatGroq error: {exc}")

        # Fallback to OpenRouter / OpenAI compatible provider if configured
        if self.openrouter_api_key:
            try:
                from langchain_community.chat_models import ChatOpenAI
                return ChatOpenAI(
                    model_name=model_name,
                    openai_api_key=self.openrouter_api_key,
                    openai_api_base="https://openrouter.ai/api/v1",
                    request_timeout=settings.LLM_TIMEOUT_SECONDS,
                )
            except Exception as exc:
                print(f"ModelRouter OpenRouter error: {exc}")

        return None


# Shared singleton router instance
model_router = ModelRouter()
