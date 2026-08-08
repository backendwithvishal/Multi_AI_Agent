import os
from pathlib import Path
from typing import List, Optional
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")


class Settings:
    def __init__(self):
        self.APP_NAME: str = "TripMate AI Multi-Agent Backend Engine"
        self.APP_VERSION: str = "3.0.0"
        self.APP_ENV: str = os.getenv("APP_ENV", "development").lower()

        # Security & Auth
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

        # External API Keys
        self.GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "").strip()
        self.TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "").strip()
        self.OPENWEATHER_API_KEY: str = os.getenv("OPENWEATHER_API_KEY", "").strip()
        self.AVIATIONSTACK_API_KEY: str = (
            os.getenv("AVIATIONSTACK_API_KEY")
            or os.getenv("AVIATION_STACK_API_KEY", "")
        ).strip()

        # Database Configuration
        self.DATABASE_URL: Optional[str] = os.getenv("DATABASE_URL", "").strip() or None

        # Concurrency & Performance
        self.CACHE_TTL_SECONDS: int = int(os.getenv("CACHE_TTL_SECONDS", "3600"))
        self.CACHE_MAX_ENTRIES: int = int(os.getenv("CACHE_MAX_ENTRIES", "1000"))
        self.RATE_LIMIT_REQUESTS: int = int(os.getenv("RATE_LIMIT_REQUESTS", "30"))
        self.RATE_LIMIT_WINDOW_SECONDS: int = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))

        # Timeouts
        self.LLM_TIMEOUT_SECONDS: float = float(os.getenv("LLM_TIMEOUT_SECONDS", "30.0"))
        self.MCP_TIMEOUT_SECONDS: float = float(os.getenv("MCP_TIMEOUT_SECONDS", "15.0"))
        self.EXTERNAL_API_TIMEOUT_SECONDS: float = float(
            os.getenv("EXTERNAL_API_TIMEOUT_SECONDS", "10.0")
        )

        # Logging
        self.LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()

    def validate_production(self) -> None:
        if self.APP_ENV == "production":
            missing = []
            if not self.GROQ_API_KEY:
                missing.append("GROQ_API_KEY")
            if missing:
                raise ValueError(
                    f"Production startup failed! Mandatory configuration missing: {', '.join(missing)}"
                )


settings = Settings()
