"""
Typed Settings & Environment Configuration Module

Built on pydantic-settings with strict validation:
- Application Metadata (APP_NAME, APP_VERSION, APP_ENV, ENV)
- Security & Auth (API_KEY, ADMIN_REGISTRATION_SECRET, AUTH_REQUIRED, ALLOWED_ORIGINS)
- API Keys (Groq, OpenRouter, HuggingFace, Tavily, OpenWeather, AviationStack)
- Persistence & Caching (DATABASE_URL, REDIS_URL)
- Cost & Rate Control (RATE_LIMIT_REQUESTS, DAILY_TOKEN_BUDGET_PER_USER, RECURSION_LIMIT)
- Proxy & Network Boundaries (TRUSTED_PROXIES, TOOL_ALLOWED_HOSTS, MAX_REQUEST_BODY_BYTES)
"""

import os
from importlib.metadata import version as _pkg_version, PackageNotFoundError
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if os.getenv("APP_ENV") not in ("test", "testing") and os.getenv("ENV") not in ("test", "testing"):
    load_dotenv(BASE_DIR / ".env")


def _get_version() -> str:
    """Single-source of truth: reads version from pyproject.toml via importlib.metadata.
    Falls back to reading pyproject.toml directly if the package is not installed.
    """
    try:
        return _pkg_version("multi-ai-agent")
    except PackageNotFoundError:
        pass
    try:
        import tomllib  # Python 3.11+
        toml_path = BASE_DIR / "pyproject.toml"
        with open(toml_path, "rb") as fh:
            data = tomllib.load(fh)
        return data["project"]["version"]
    except Exception:
        return "3.0.0"  # fallback


# =========================================================
# Legacy Parsing Helper Functions (Preserved for compatibility)
# =========================================================

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
    """Safely converts environment variable to float with concatenation detection."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    cleaned = raw.strip()

    if cleaned.count(".") > 1:
        raise ValueError(
            f"Invalid configuration for '{name}': value '{raw}' looks like two numbers "
            f"concatenated together (e.g. '10.0' + '10.0' → '10.010.0'). "
            f"Check for duplicate definitions of {name}."
        )

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


# =========================================================
# Pydantic Typed Settings Class
# =========================================================

class Settings(BaseSettings):
    """Central configuration class loading environment settings with pydantic validation."""

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "Multi-AI-Agent"
    APP_VERSION: str = _get_version()
    APP_ENV: str = Field(default="development")
    ENV: str = Field(default="")

    # Security & Authentication settings
    API_KEY: Optional[str] = None
    JWT_SECRET_KEY: Optional[str] = None
    ADMIN_REGISTRATION_SECRET: Optional[str] = None
    AUTH_REQUIRED: bool = False
    ALLOWED_ORIGINS: Union[List[str], str] = Field(default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"])

    # External API Keys for AI & MCP services
    GROQ_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""
    HUGGINGFACE_API_KEY: str = ""
    TAVILY_API_KEY: str = ""
    OPENWEATHER_API_KEY: str = ""
    AVIATIONSTACK_API_KEY: str = ""

    # Model Tier Selection
    FAST_LLM_MODEL: str = "llama-3.1-8b-instant"
    REASONING_LLM_MODEL: str = "llama-3.3-70b-versatile"
    OPENROUTER_FAST_MODEL: str = "meta-llama/llama-3.1-8b-instruct:free"
    OPENROUTER_REASONING_MODEL: str = "meta-llama/llama-3.3-70b-instruct:free"
    HUGGINGFACE_FAST_MODEL: str = "meta-llama/Meta-Llama-3-8B-Instruct"
    HUGGINGFACE_REASONING_MODEL: str = "meta-llama/Llama-3.3-70B-Instruct"

    # Server & Process Concurrency
    PORT: int = 8000
    WEB_CONCURRENCY: int = 2
    GRACEFUL_TIMEOUT: int = 30
    KEEP_ALIVE: int = 5

    # LangSmith Observability & Tracing settings
    LANGCHAIN_TRACING_V2: str = "false"
    LANGCHAIN_API_KEY: str = ""
    LANGCHAIN_PROJECT: str = "tripmate-ai"
    LANGCHAIN_ENDPOINT: str = "https://api.smith.langchain.com"

    # Datastore URLs
    DATABASE_URL: Optional[str] = None
    REDIS_URL: Optional[str] = None

    # Performance & Rate Limits
    CACHE_TTL_SECONDS: int = 3600
    CACHE_MAX_ENTRIES: int = 1000
    RATE_LIMIT_REQUESTS: int = 30
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    # Cost & Abuse Controls
    DAILY_TOKEN_BUDGET_PER_USER: int = 100_000
    LANGGRAPH_RECURSION_LIMIT: int = 15
    MAX_PARALLEL_AGENTS: int = 4
    FAIL_OPEN_REDIS: bool = False  # Fail-closed for LLM routes by default
    EMERGENCY_IN_MEMORY_RATE_LIMIT: int = 5  # Small emergency cap if Redis is down

    # Proxy Awareness & Ingress Boundaries
    TRUSTED_PROXIES: Union[List[str], str] = Field(default_factory=lambda: ["127.0.0.1", "::1"])
    MAX_REQUEST_BODY_BYTES: int = 1_048_576  # 1 MB
    MAX_MESSAGE_LENGTH: int = 2000
    MAX_FEEDBACK_LENGTH: int = 1000
    THREAD_ID_REGEX: str = r"^[a-zA-Z0-9_-]{8,128}$"
    ENABLE_DOCS_IN_PROD: bool = False

    # SSRF & Outbound Boundaries
    TOOL_ALLOWED_HOSTS: Union[List[str], str] = Field(
        default_factory=lambda: [
            "api.openweathermap.org",
            "mcp.tavily.com",
            "api.aviationstack.com",
            "api.groq.com",
            "openrouter.ai",
        ]
    )
    MAX_TOOL_OUTPUT_BYTES: int = 50_000

    # External Service Timeouts (Seconds)
    LLM_TIMEOUT_SECONDS: float = 30.0
    MCP_TIMEOUT_SECONDS: float = 15.0
    EXTERNAL_API_TIMEOUT_SECONDS: float = 10.0

    # Database Pool Settings
    DB_POOL_MIN_SIZE: int = 1
    DB_POOL_MAX_SIZE: int = 10
    DB_POOL_TIMEOUT_SECONDS: float = 10.0

    # Human-In-The-Loop Approval Settings
    APPROVAL_TTL_SECONDS: int = 900  # 15 minutes TTL for pending approvals

    # MCP Cache Settings
    MCP_CACHE_TTL_SECONDS: int = 3600
    MCP_CACHE_MAX_BYTES: int = 65_536  # 64 KB per-key limit

    # Logging & Observability Settings
    LOG_LEVEL: str = "INFO"
    CAPTURE_PROMPTS: bool = False  # Prompt capture OFF by default to avoid data leakage
    OTEL_ENABLED: bool = False  # OpenTelemetry distributed tracing toggle
    METRICS_PROTECTED: bool = True  # Protect /metrics endpoint from public scrapers
    METRICS_TOKEN: Optional[str] = None
    METRICS_ALLOWED_IPS: Union[List[str], str] = Field(default_factory=lambda: ["127.0.0.1", "::1", "testclient"])

    @field_validator("ALLOWED_ORIGINS", "TRUSTED_PROXIES", "TOOL_ALLOWED_HOSTS", "METRICS_ALLOWED_IPS", mode="before")
    @classmethod
    def _parse_list_fields(cls, v):
        if isinstance(v, str):
            cleaned = v.strip()
            if cleaned.startswith("[") and cleaned.endswith("]"):
                import json
                try:
                    return json.loads(cleaned)
                except Exception:
                    pass
            return [x.strip() for x in cleaned.split(",") if x.strip()]
        return v

    def __init__(self, **values):
        super().__init__(**values)

        # Synchronize ENV and APP_ENV: explicit constructor values take highest precedence
        explicit_env = values.get("APP_ENV") or values.get("ENV")
        raw_env = (
            explicit_env
            or ("test" if (os.getenv("APP_ENV") in ("test", "testing") or os.getenv("ENV") in ("test", "testing")) else None)
            or os.getenv("ENV")
            or os.getenv("APP_ENV")
            or self.ENV
            or self.APP_ENV
        )
        env_from_os = (raw_env or "dev").strip().lower()
        if env_from_os in ("prod", "production"):
            self.APP_ENV = "production"
            self.ENV = "prod"
        elif env_from_os in ("dev", "development"):
            self.APP_ENV = "development"
            self.ENV = "dev"
        elif env_from_os in ("test", "testing"):
            self.APP_ENV = "test"
            self.ENV = "test"
        else:
            self.APP_ENV = env_from_os
            self.ENV = env_from_os

        # Fallback aliases from environment if not populated
        if not self.API_KEY:
            self.API_KEY = _parse_str("API_KEY") or None
        if not self.ADMIN_REGISTRATION_SECRET:
            self.ADMIN_REGISTRATION_SECRET = _parse_str("ADMIN_REGISTRATION_SECRET") or None

        # Parse boolean AUTH_REQUIRED
        raw_auth = os.getenv("AUTH_REQUIRED")
        if raw_auth is not None:
            self.AUTH_REQUIRED = _parse_bool("AUTH_REQUIRED", False)
        elif self.is_production:
            self.AUTH_REQUIRED = True

        # Parse ALLOWED_ORIGINS if set in os.environ
        raw_origins = os.getenv("ALLOWED_ORIGINS")
        if raw_origins:
            self.ALLOWED_ORIGINS = _parse_list("ALLOWED_ORIGINS", self.ALLOWED_ORIGINS)

        # External Keys
        if not self.GROQ_API_KEY:
            self.GROQ_API_KEY = _parse_str("GROQ_API_KEY")
        if not self.OPENROUTER_API_KEY:
            self.OPENROUTER_API_KEY = _parse_str("OPENROUTER_API_KEY")
        if not self.HUGGINGFACE_API_KEY:
            self.HUGGINGFACE_API_KEY = _parse_str("HUGGINGFACE_API_KEY") or _parse_str("HUGGING_FACE_API_KEY")
        if not self.TAVILY_API_KEY:
            self.TAVILY_API_KEY = _parse_str("TAVILY_API_KEY")
        if not self.OPENWEATHER_API_KEY:
            self.OPENWEATHER_API_KEY = _parse_str("OPENWEATHER_API_KEY")
        if not self.AVIATIONSTACK_API_KEY:
            self.AVIATIONSTACK_API_KEY = _parse_str("AVIATIONSTACK_API_KEY") or _parse_str("AVIATION_STACK_API_KEY")

        # Datastores
        if not self.DATABASE_URL:
            self.DATABASE_URL = _parse_str("DATABASE_URL") or None
        if not self.REDIS_URL:
            self.REDIS_URL = _parse_str("REDIS_URL") or None

        # Parsed limits
        if "RATE_LIMIT_REQUESTS" in os.environ:
            self.RATE_LIMIT_REQUESTS = _parse_int("RATE_LIMIT_REQUESTS", self.RATE_LIMIT_REQUESTS)
        if "RATE_LIMIT_WINDOW_SECONDS" in os.environ:
            self.RATE_LIMIT_WINDOW_SECONDS = _parse_int("RATE_LIMIT_WINDOW_SECONDS", self.RATE_LIMIT_WINDOW_SECONDS)
        if "EXTERNAL_API_TIMEOUT_SECONDS" in os.environ:
            self.EXTERNAL_API_TIMEOUT_SECONDS = _parse_float("EXTERNAL_API_TIMEOUT_SECONDS", self.EXTERNAL_API_TIMEOUT_SECONDS)
        if "LLM_TIMEOUT_SECONDS" in os.environ:
            self.LLM_TIMEOUT_SECONDS = _parse_float("LLM_TIMEOUT_SECONDS", self.LLM_TIMEOUT_SECONDS)
        if "MCP_TIMEOUT_SECONDS" in os.environ:
            self.MCP_TIMEOUT_SECONDS = _parse_float("MCP_TIMEOUT_SECONDS", self.MCP_TIMEOUT_SECONDS)
        if "TRUSTED_PROXIES" in os.environ:
            self.TRUSTED_PROXIES = _parse_list("TRUSTED_PROXIES", self.TRUSTED_PROXIES)
        if "CAPTURE_PROMPTS" in os.environ:
            self.CAPTURE_PROMPTS = _parse_bool("CAPTURE_PROMPTS", self.CAPTURE_PROMPTS)
        if "OTEL_ENABLED" in os.environ or "ENABLE_OTEL" in os.environ:
            self.OTEL_ENABLED = _parse_bool("OTEL_ENABLED", _parse_bool("ENABLE_OTEL", self.OTEL_ENABLED))
        if "METRICS_PROTECTED" in os.environ:
            self.METRICS_PROTECTED = _parse_bool("METRICS_PROTECTED", self.METRICS_PROTECTED)
        if "METRICS_TOKEN" in os.environ:
            self.METRICS_TOKEN = _parse_str("METRICS_TOKEN") or None

        # Safeguard LangSmith auth and prompt privacy
        if self.LANGCHAIN_TRACING_V2 == "true" and not self.LANGCHAIN_API_KEY:
            self.LANGCHAIN_TRACING_V2 = "false"
            os.environ["LANGCHAIN_TRACING_V2"] = "false"

        if not self.CAPTURE_PROMPTS:
            os.environ["LANGCHAIN_HIDE_INPUTS"] = "true"
            os.environ["LANGCHAIN_HIDE_OUTPUTS"] = "true"

    @property
    def is_production(self) -> bool:
        """Returns True if running in production mode."""
        return self.APP_ENV in ("production", "prod") or self.ENV in ("production", "prod")

    @property
    def is_dev(self) -> bool:
        """Returns True if running in development mode."""
        return self.APP_ENV in ("development", "dev") or self.ENV in ("development", "dev")

    @property
    def is_test(self) -> bool:
        """Returns True if running under pytest or test environment."""
        import sys
        return (
            self.APP_ENV in ("test", "testing")
            or self.ENV in ("test", "testing")
            or os.getenv("APP_ENV") in ("test", "testing")
            or os.getenv("ENV") in ("test", "testing")
            or "pytest" in sys.modules
            or "PYTEST_CURRENT_TEST" in os.environ
            or any("pytest" in str(arg).lower() for arg in sys.argv)
        )

    def validate_production(self) -> None:
        """Validates that mandatory API keys and security configs are present when running in production mode."""
        if self.is_production:
            missing = []
            has_llm = bool(self.GROQ_API_KEY or self.OPENROUTER_API_KEY or self.HUGGINGFACE_API_KEY)
            if not has_llm:
                missing.append("At least one LLM Provider Key (GROQ_API_KEY, OPENROUTER_API_KEY, or HUGGINGFACE_API_KEY)")
            if not self.API_KEY:
                missing.append("API_KEY (used for authorization and token signing)")
            if missing:
                raise ValueError(
                    f"Production startup failed! Mandatory configuration missing: {', '.join(missing)}"
                )
            if self.JWT_SECRET_KEY and self.JWT_SECRET_KEY in ("dev_jwt_secret_key_change_in_prod", "secret", "change-me", ""):
                raise ValueError(
                    "Production startup failed! JWT_SECRET_KEY must be changed from default development secret."
                )

            if "*" in self.ALLOWED_ORIGINS and self.AUTH_REQUIRED and getattr(self, "CORS_ALLOW_CREDENTIALS", False):
                raise ValueError(
                    "Production startup failed! Wildcard origin '*' cannot be combined with credentials."
                )


# Global singleton settings object
settings = Settings()
