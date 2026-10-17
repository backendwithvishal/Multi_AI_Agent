import asyncio
import logging
from typing import Any, Dict, Iterator, Optional, Sequence

logger = logging.getLogger("tripmate.database")

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None
    dict_row = None

try:
    from psycopg_pool import ConnectionPool
except ImportError:
    ConnectionPool = None

try:
    from langgraph.checkpoint.base import (
        BaseCheckpointSaver,
        ChannelVersions,
        Checkpoint,
        CheckpointMetadata,
        CheckpointTuple,
    )
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.checkpoint.postgres import PostgresSaver
except ImportError:
    BaseCheckpointSaver = object  # type: ignore
    ChannelVersions = Any  # type: ignore
    Checkpoint = Any  # type: ignore
    CheckpointMetadata = Any  # type: ignore
    CheckpointTuple = Any  # type: ignore
    MemorySaver = None
    PostgresSaver = None

from tripmate.config.settings import settings

_db_pool: Optional[Any] = None
checkpointer_pool: Optional[Any] = None


class PostgresCheckpointer(BaseCheckpointSaver):
    """
    Robust thread-safe PostgreSQL checkpointer bridging synchronous pooling with
    both synchronous and asynchronous LangGraph workflow executions.
    """

    def __init__(self, saver: Any, pool: Optional[Any] = None):
        super().__init__()
        self.saver = saver
        self.pool = pool

    def get_tuple(self, config: Dict[str, Any]) -> Optional[Any]:
        return self.saver.get_tuple(config)

    def list(
        self,
        config: Optional[Dict[str, Any]],
        *,
        filter: Optional[Dict[str, Any]] = None,
        before: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
    ) -> Iterator[Any]:
        return self.saver.list(config, filter=filter, before=before, limit=limit)

    def put(
        self,
        config: Dict[str, Any],
        checkpoint: Any,
        metadata: Any,
        new_versions: Any,
    ) -> Dict[str, Any]:
        return self.saver.put(config, checkpoint, metadata, new_versions)

    def put_writes(self, config: Dict[str, Any], writes: Sequence[Any], task_id: str) -> None:
        return self.saver.put_writes(config, writes, task_id)

    async def aget_tuple(self, config: Dict[str, Any]) -> Optional[Any]:
        return await asyncio.to_thread(self.saver.get_tuple, config)

    async def alist(
        self,
        config: Optional[Dict[str, Any]],
        *,
        filter: Optional[Dict[str, Any]] = None,
        before: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
    ):
        items = await asyncio.to_thread(
            lambda: list(self.saver.list(config, filter=filter, before=before, limit=limit))
        )
        for item in items:
            yield item

    async def aput(
        self,
        config: Dict[str, Any],
        checkpoint: Any,
        metadata: Any,
        new_versions: Any,
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(self.saver.put, config, checkpoint, metadata, new_versions)

    async def aput_writes(self, config: Dict[str, Any], writes: Sequence[Any], task_id: str) -> None:
        return await asyncio.to_thread(self.saver.put_writes, config, writes, task_id)


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


def get_db_pool() -> Optional[Any]:
    """Returns singleton thread-safe ConnectionPool for synchronous application operations."""
    global _db_pool
    if _db_pool is not None and not _db_pool.closed:
        return _db_pool

    url = get_formatted_db_url()
    if not url or not psycopg or not ConnectionPool:
        return None

    try:
        _db_pool = ConnectionPool(
            url,
            min_size=1,
            max_size=10,
            kwargs={"row_factory": dict_row},
            open=True,
        )
        return _db_pool
    except Exception as exc:
        logger.warning(f"Failed to initialize database connection pool: {exc}")
        return None


def close_db_pools():
    """Closes all database connection pools on shutdown."""
    global _db_pool, checkpointer_pool
    if _db_pool is not None:
        try:
            _db_pool.close()
        except Exception:
            pass
        _db_pool = None

    if checkpointer_pool is not None:
        try:
            checkpointer_pool.close()
        except Exception:
            pass
        checkpointer_pool = None


import atexit
atexit.register(close_db_pools)


def check_db_health() -> Dict[str, Any]:
    url = get_formatted_db_url()
    if not url or not psycopg:
        return {
            "status": "disabled",
            "message": "DATABASE_URL not configured. Development mode using in-memory store.",
            "connected": False,
        }

    try:
        with psycopg.connect(url, connect_timeout=3, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 AS alive")
                res = cur.fetchone()
                if not res or res.get("alive") != 1:
                    return {
                        "status": "unhealthy",
                        "message": "Database query probe failed",
                        "connected": False,
                    }

                cur.execute(
                    """
                    SELECT table_name FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name IN ('users', 'watchlists', 'alerts', 'assets', 'thread_ownership');
                    """
                )
                tables = [r["table_name"] for r in cur.fetchall()]
                expected_tables = ["users", "watchlists", "alerts", "assets", "thread_ownership"]
                missing = [t for t in expected_tables if t not in tables]

                if missing:
                    return {
                        "status": "degraded",
                        "message": f"Database connected but required tables missing: {', '.join(missing)}. Migrations pending.",
                        "connected": True,
                        "tables_found": len(tables),
                    }

                return {
                    "status": "healthy",
                    "message": "PostgreSQL database connection active and schema verified",
                    "connected": True,
                    "tables": len(tables),
                }
    except Exception as exc:
        return {
            "status": "unhealthy",
            "message": "Database connection probe failed",
            "connected": False,
        }


def initialize_checkpointer():
    global checkpointer_pool
    db_url = get_formatted_db_url()

    if db_url and psycopg and PostgresSaver and ConnectionPool:
        try:
            with psycopg.connect(db_url, autocommit=True, row_factory=dict_row) as sync_conn:
                sync_saver = PostgresSaver(sync_conn)
                sync_saver.setup()

            checkpointer_pool = ConnectionPool(
                db_url,
                min_size=1,
                max_size=10,
                kwargs={"row_factory": dict_row},
                open=True,
            )
            saver = PostgresSaver(checkpointer_pool)
            pg_checkpointer = PostgresCheckpointer(saver, checkpointer_pool)
            print("PostgresSaver checkpointer successfully initialized.")
            return pg_checkpointer
        except Exception as exc:
            if settings.APP_ENV == "production":
                raise RuntimeError(
                    f"Production startup failed: PostgreSQL checkpointer initialization error: {exc}"
                )
            print(f"PostgreSQL connection failed ({exc}). Falling back to MemorySaver for development.")

    if settings.APP_ENV == "production":
        print("WARNING: DATABASE_URL not configured. Running in production mode with MemorySaver checkpointer.")

    return MemorySaver() if MemorySaver else None


checkpointer = initialize_checkpointer()
