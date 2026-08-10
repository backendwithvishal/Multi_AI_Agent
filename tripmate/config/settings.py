"""
Typed Settings & Environment Configuration Module

This module loads variables from `.env` and provides typed settings used across the app:
- Application Metadata (APP_NAME, APP_VERSION, APP_ENV)
- API Keys (Groq, Tavily, OpenWeather, AviationStack)
- Database URL & persistent checkpointing settings
- Performance tuning (Cache TTL, Max entries, Rate limit thresholds)
- Timeout limits for LLM and external MCP tools
"""

import os
from pathlib import Path
from typing import List, Optional
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")


def _parse_str(name: str, default: str = "") -> str:
    """Reads a string environment variable with whitespace stripping and fallback."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip()


def _parse_int(name: str, default: int) -> int:
    """Safely converts environment variable to integer with clear error reporting."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    cleaned = raw.strip()
    try:
        return int(cleaned)
    except ValueError as exc:
        raise ValueError(
            f"Invalid configuration for '{name}': expected integer, got '{raw}'. "
            f"Please verify {name} in your .env file or environment variables."
        ) from exc


def _parse_float(name: str, default: float) -> float:
    """Safely converts environment variable to float with clear error reporting."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    cleaned = raw.strip()
    try:
        return float(cleaned)
    except ValueError as exc:
        raise ValueError(
            f"Invalid configuration for '{name}': expected valid float/number, got '{raw}'. "
            f"Please verify {name} in your .env file or environment variables."
        ) from exc


def _parse_bool(name: str, default: bool) -> bool:
    """Safely parses boolean environment variable handling true/false/1/0/yes/no."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    cleaned = raw.strip().lower()
    if cleaned in ("true", "1", "yes", "on"):
        return True
    if cleaned in ("false", "0", "no", "off"):
        return False
    raise ValueError(
        f"Invalid configuration for '{name}': expected boolean (true/false, 1/0, yes/no), got '{raw}'. "
        f"Please verify {name} in your .env file or environment variables."
    )


def _parse_list(name: str, default: List[str]) -> List[str]:
    """Parses a comma-separated environment variable string into a clean list."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]


class Settings:
    """Central configuration class loading environment settings with safe defaults and explicit validation."""

    def __init__(self):
        self.APP_NAME: str = "TripMate AI Multi-Agent Backend Engine"
        self.APP_VERSION: str = "3.0.0"
        self.APP_ENV: str = _parse_str("APP_ENV", "development").lower()

        # Security & Authentication settings
        self.API_KEY: Optional[str] = _parse_str("API_KEY") or None
        self.AUTH_REQUIRED: bool = (
            _parse_bool("AUTH_REQUIRED", False)
            or self.APP_ENV == "production"
        )
        self.ALLOWED_ORIGINS: List[str] = _parse_list("ALLOWED_ORIGINS", ["*"])

        # External API Keys for AI & MCP services
        self.GROQ_API_KEY: str = _parse_str("GROQ_API_KEY")
        self.OPENROUTER_API_KEY: str = _parse_str("OPENROUTER_API_KEY")
        self.TAVILY_API_KEY: str = _parse_str("TAVILY_API_KEY")
        self.OPENWEATHER_API_KEY: str = _parse_str("OPENWEATHER_API_KEY")
        self.AVIATIONSTACK_API_KEY: str = (
            _parse_str("AVIATIONSTACK_API_KEY")
            or _parse_str("AVIATION_STACK_API_KEY")
        )

        # LangSmith Observability & Tracing settings
        self.LANGCHAIN_TRACING_V2: str = _parse_str("LANGCHAIN_TRACING_V2", "false")
        self.LANGCHAIN_API_KEY: str = _parse_str("LANGCHAIN_API_KEY")
        self.LANGCHAIN_PROJECT: str = _parse_str("LANGCHAIN_PROJECT", "tripmate-ai")
        self.LANGCHAIN_ENDPOINT: str = _parse_str("LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com")

        if self.LANGCHAIN_API_KEY and _parse_bool("LANGCHAIN_TRACING_V2", False):
            os.environ["LANGCHAIN_TRACING_V2"] = "true"
            os.environ["LANGCHAIN_API_KEY"] = self.LANGCHAIN_API_KEY
            os.environ["LANGCHAIN_PROJECT"] = self.LANGCHAIN_PROJECT
            os.environ["LANGCHAIN_ENDPOINT"] = self.LANGCHAIN_ENDPOINT

        # PostgreSQL Database Connection String
        self.DATABASE_URL: Optional[str] = _parse_str("DATABASE_URL") or None

        # Performance & Rate Limits
        self.CACHE_TTL_SECONDS: int = _parse_int("CACHE_TTL_SECONDS", 3600)
        self.CACHE_MAX_ENTRIES: int = _parse_int("CACHE_MAX_ENTRIES", 1000)
        self.RATE_LIMIT_REQUESTS: int = _parse_int("RATE_LIMIT_REQUESTS", 500)
        self.RATE_LIMIT_WINDOW_SECONDS: int = _parse_int("RATE_LIMIT_WINDOW_SECONDS", 60)

        # External Service Timeouts (Seconds)
        self.LLM_TIMEOUT_SECONDS: float = _parse_float("LLM_TIMEOUT_SECONDS", 30.0)
        self.MCP_TIMEOUT_SECONDS: float = _parse_float("MCP_TIMEOUT_SECONDS", 15.0)
        self.EXTERNAL_API_TIMEOUT_SECONDS: float = _parse_float(
            "EXTERNAL_API_TIMEOUT_SECONDS", 10.0
        )

        # Logging level
        self.LOG_LEVEL: str = _parse_str("LOG_LEVEL", "INFO").upper()

    def validate_production(self) -> None:
        """Validates that mandatory API keys are present when running in production mode."""
        if self.APP_ENV == "production":
            missing = []
            if not self.GROQ_API_KEY:
                missing.append("GROQ_API_KEY")
            if missing:
                raise ValueError(
                    f"Production startup failed! Mandatory configuration missing: {', '.join(missing)}"
                )


# Global singleton settings object
settings = Settings()
