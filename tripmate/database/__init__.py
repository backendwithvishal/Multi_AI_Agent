import os
from typing import Dict, Any, Optional

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None
    dict_row = None

try:
    from langgraph.checkpoint.postgres import PostgresSaver
    from langgraph.checkpoint.memory import MemorySaver
except ImportError:
    PostgresSaver = None
    MemorySaver = None

from tripmate.config.settings import settings


def get_formatted_db_url() -> Optional[str]:
    """
    Returns the database connection URL formatted with appropriate SSL parameters.
    
    - If `sslmode` is explicitly set in `DATABASE_URL`, respects the provided parameter.
    - For local development and Docker container networks (e.g. `localhost`, `127.0.0.1`, `postgres_db`),
      does not force `sslmode=require` since standard local PostgreSQL instances do not enable SSL by default.
    - For production cloud databases, defaults to `sslmode=require` if not explicitly specified.
    """
    url = settings.DATABASE_URL
    if not url:
        return None
    if "sslmode=" in url:
        return url

    lower_url = url.lower()
    if (
        settings.APP_ENV == "development"
        or "localhost" in lower_url
        or "127.0.0.1" in lower_url
        or "postgres_db" in lower_url
        or "@postgres" in lower_url
    ):
        return url

    separator = "&" if "?" in url else "?"
    return f"{url}{separator}sslmode=require"


def check_db_health() -> Dict[str, Any]:
    url = get_formatted_db_url()
    if not url or not psycopg:
        return {
            "status": "disabled",
            "message": "DATABASE_URL not configured. Development mode using MemorySaver checkpointer.",
            "connected": False,
        }

    try:
        with psycopg.connect(url, connect_timeout=3, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 AS alive")
                res = cur.fetchone()
                if res and res.get("alive") == 1:
                    return {
                        "status": "healthy",
                        "message": "PostgreSQL database connection active",
                        "connected": True,
                    }
    except Exception as exc:
        return {
            "status": "unhealthy",
            "message": f"Database connection probe failed: {exc}",
            "connected": False,
        }

    return {
        "status": "unhealthy",
        "message": "Unknown database connectivity error",
        "connected": False,
    }


def initialize_checkpointer():
    db_url = get_formatted_db_url()

    if db_url and psycopg and PostgresSaver:
        try:
            conn = psycopg.connect(db_url, autocommit=True, row_factory=dict_row)
            saver = PostgresSaver(conn)
            saver.setup()
            print("PostgresSaver checkpointer successfully initialized.")
            return saver
        except Exception as exc:
            if settings.APP_ENV == "production":
                raise RuntimeError(
                    f"Production startup failed: PostgreSQL checkpointer initialization error: {exc}"
                )
            print(f"PostgreSQL connection failed ({exc}). Falling back to MemorySaver for development.")

    if settings.APP_ENV == "production":
        raise RuntimeError("Production startup failed: DATABASE_URL mandatory for persistent workflow state.")

    return MemorySaver() if MemorySaver else None


checkpointer = initialize_checkpointer()
