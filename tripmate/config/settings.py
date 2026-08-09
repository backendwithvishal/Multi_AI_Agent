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


class Settings:
    """Central configuration class loading environment settings with safe defaults."""

    def __init__(self):
        self.APP_NAME: str = "TripMate AI Multi-Agent Backend Engine"
        self.APP_VERSION: str = "3.0.0"
        self.APP_ENV: str = os.getenv("APP_ENV", "development").lower()

        # Security & Authentication settings
        self.API_KEY: Optional[str] = os.getenv("API_KEY", "").strip() or None
        self.AUTH_REQUIRED: bool = (
            os.getenv("AUTH_REQUIRED", "false").lower() == "true"
            or self.APP_ENV == "production"
        )
        self.ALLOWED_ORIGINS: List[str] = [
            origin.strip()
            for origin in os.getenv("ALLOWED_ORIGINS", "*").split(",")
            if origin.strip()
        ]

        # External API Keys for AI & MCP services
        self.GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "").strip()
        self.TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "").strip()
        self.OPENWEATHER_API_KEY: str = os.getenv("OPENWEATHER_API_KEY", "").strip()
        self.AVIATIONSTACK_API_KEY: str = (
            os.getenv("AVIATIONSTACK_API_KEY")
            or os.getenv("AVIATION_STACK_API_KEY", "")
        ).strip()

        # LangSmith Observability & Tracing settings
        self.LANGCHAIN_TRACING_V2: str = os.getenv("LANGCHAIN_TRACING_V2", "false").strip()
        self.LANGCHAIN_API_KEY: str = os.getenv("LANGCHAIN_API_KEY", "").strip()
        self.LANGCHAIN_PROJECT: str = os.getenv("LANGCHAIN_PROJECT", "tripmate-ai").strip()
        self.LANGCHAIN_ENDPOINT: str = os.getenv("LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com").strip()

        if self.LANGCHAIN_API_KEY and self.LANGCHAIN_TRACING_V2.lower() == "true":
            os.environ["LANGCHAIN_TRACING_V2"] = "true"
            os.environ["LANGCHAIN_API_KEY"] = self.LANGCHAIN_API_KEY
            os.environ["LANGCHAIN_PROJECT"] = self.LANGCHAIN_PROJECT
            os.environ["LANGCHAIN_ENDPOINT"] = self.LANGCHAIN_ENDPOINT

        # PostgreSQL Database Connection String
        self.DATABASE_URL: Optional[str] = os.getenv("DATABASE_URL", "").strip() or None

        # Performance & Rate Limits
        self.CACHE_TTL_SECONDS: int = int(os.getenv("CACHE_TTL_SECONDS", "3600"))
        self.CACHE_MAX_ENTRIES: int = int(os.getenv("CACHE_MAX_ENTRIES", "1000"))
        self.RATE_LIMIT_REQUESTS: int = int(os.getenv("RATE_LIMIT_REQUESTS", "30"))
        self.RATE_LIMIT_WINDOW_SECONDS: int = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))

        # External Service Timeouts (Seconds)
        self.LLM_TIMEOUT_SECONDS: float = float(os.getenv("LLM_TIMEOUT_SECONDS", "30.0"))
        self.MCP_TIMEOUT_SECONDS: float = float(os.getenv("MCP_TIMEOUT_SECONDS", "15.0"))
        self.EXTERNAL_API_TIMEOUT_SECONDS: float = float(
            os.getenv("EXTERNAL_API_TIMEOUT_SECONDS", "10.0")
        )

        # Logging level
        self.LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()

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
