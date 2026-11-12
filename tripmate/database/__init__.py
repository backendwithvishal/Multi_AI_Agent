import asyncio
import logging
import os
import time
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
_db_pool_init_attempted: bool = False
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
        t0 = time.time()
        try:
            return self.saver.get_tuple(config)
        finally:
            try:
                from tripmate.middleware.metrics import metrics_registry

                metrics_registry.record_checkpoint_db_latency(time.time() - t0)
            except Exception:
                pass

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
        t0 = time.time()
        try:
            return self.saver.put(config, checkpoint, metadata, new_versions)
        finally:
            try:
                from tripmate.middleware.metrics import metrics_registry

                metrics_registry.record_checkpoint_db_latency(time.time() - t0)
            except Exception:
                pass

    def put_writes(self, config: Dict[str, Any], writes: Sequence[Any], task_id: str) -> None:
        return self.saver.put_writes(config, writes, task_id)

    async def aget_tuple(self, config: Dict[str, Any]) -> Optional[Any]:
        t0 = time.time()
        try:
            return await asyncio.to_thread(self.saver.get_tuple, config)
        finally:
            try:
                from tripmate.middleware.metrics import metrics_registry

                metrics_registry.record_checkpoint_db_latency(time.time() - t0)
            except Exception:
                pass

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
        t0 = time.time()
        try:
            return await asyncio.to_thread(self.saver.put, config, checkpoint, metadata, new_versions)
        finally:
            try:
                from tripmate.middleware.metrics import metrics_registry

                metrics_registry.record_checkpoint_db_latency(time.time() - t0)
            except Exception:
                pass

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
    global _db_pool, _db_pool_init_attempted
    if _db_pool is not None and not _db_pool.closed:
        return _db_pool
    if _db_pool_init_attempted and _db_pool is None:
        return None

    if settings.is_test and not os.getenv("RUN_LIVE_DB_TESTS"):
        _db_pool_init_attempted = True
        return None

    url = get_formatted_db_url()
    if not url or not psycopg or not ConnectionPool:
        _db_pool_init_attempted = True
        return None

    try:
        # Quick connectivity test with connect_timeout so we don't stall dev/test runs
        with psycopg.connect(url, connect_timeout=2) as test_conn:
            with test_conn.cursor() as cur:
                cur.execute("SELECT 1;")

        _db_pool = ConnectionPool(
            url,
            min_size=settings.DB_POOL_MIN_SIZE,
            max_size=settings.DB_POOL_MAX_SIZE,
            timeout=settings.DB_POOL_TIMEOUT_SECONDS,
            check=getattr(ConnectionPool, "check_connection", None),
            kwargs={"row_factory": dict_row},
            open=True,
        )
        _db_pool_init_attempted = True
        return _db_pool
    except Exception as exc:
        _db_pool_init_attempted = True
        if settings.is_production:
            logger.error(f"Failed to initialize database connection pool in production: {exc}")
            raise
        logger.info(f"Database connection pool unavailable ({exc}). Using in-memory store for development.")
        return None


def close_db_pools():
    """Closes all database connection pools on shutdown."""
    global _db_pool, _db_pool_init_attempted, checkpointer_pool
    if _db_pool is not None:
        try:
            _db_pool.close()
        except Exception:
            pass
        _db_pool = None
        _db_pool_init_attempted = False

    if checkpointer_pool is not None:
        try:
            checkpointer_pool.close()
        except Exception:
            pass
        checkpointer_pool = None


import atexit

atexit.register(close_db_pools)


def check_db_health() -> Dict[str, Any]:
    if settings.is_test and not os.getenv("RUN_LIVE_DB_TESTS"):
        return {
            "status": "healthy",
            "message": "Test mode database stub",
            "connected": True,
        }

    url = get_formatted_db_url()
    if not url or not psycopg:
        return {
            "status": "disabled",
            "message": "DATABASE_URL not configured. Development mode using in-memory store.",
            "connected": False,
        }

    pool = get_db_pool()
    # In dev or test mode, if the connection pool is not active, return disabled immediately
    # to avoid blocking on unresponsive network hosts.
    if (settings.is_dev or settings.is_test) and pool is None:
        return {
            "status": "disabled",
            "message": "Database pool not connected. Running in memory fallback mode.",
            "connected": False,
        }

    try:
        if pool and not pool.closed:
            with pool.connection(timeout=2.0) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 AS alive")
                    res = cur.fetchone()
                    if not res or res.get("alive") != 1:
                        return {
                            "status": "unhealthy",
                            "message": "Database query probe failed",
                            "connected": False,
                        }
                    return {
                        "status": "healthy",
                        "message": "PostgreSQL database connection active and pool verified",
                        "connected": True,
                    }
        else:
            with psycopg.connect(url, connect_timeout=2, row_factory=dict_row) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 AS alive")
                    res = cur.fetchone()
                    if not res or res.get("alive") != 1:
                        return {
                            "status": "unhealthy",
                            "message": "Database query probe failed",
                            "connected": False,
                        }
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


def setup_checkpoint_tables(db_url: Optional[str] = None) -> bool:
    """Explicitly and idempotently initializes LangGraph PostgresSaver tables in PostgreSQL."""
    url = db_url or get_formatted_db_url()
    if not url or not psycopg or not PostgresSaver:
        return False
    try:
        with psycopg.connect(url, connect_timeout=2, autocommit=True, row_factory=dict_row) as sync_conn:
            sync_saver = PostgresSaver(sync_conn)
            sync_saver.setup()
        logger.info("[Checkpointer] Explicit PostgreSQL checkpoint tables verified and ready.")
        return True
    except Exception as exc:
        logger.error(f"[Checkpointer] Error setting up PostgreSQL checkpoint tables: {exc}")
        raise


def initialize_checkpointer():
    """Initializes workflow checkpointer with strict production fail-fast rules.

    Rules:
    - In test mode, fallback to MemorySaver for fast unit testing unless RUN_LIVE_DB_TESTS is set.
    - In production or any environment where ENV != 'dev', PostgreSQL is strictly required.
      If PostgresSaver cannot initialize, fail startup with RuntimeError.
    - MemorySaver is ONLY permitted when ENV='dev' (or development).
    - Connection pool is configured with min/max size, timeout, and health checks.
    """
    global checkpointer_pool

    if settings.is_test and not os.getenv("RUN_LIVE_DB_TESTS"):
        return MemorySaver() if MemorySaver else None

    db_url = get_formatted_db_url()
    is_dev = (
        settings.ENV in ("dev", "development") or settings.APP_ENV in ("dev", "development") or settings.is_test
    ) and not settings.is_production

    if db_url and psycopg and PostgresSaver and ConnectionPool:
        try:
            setup_checkpoint_tables(db_url)

            checkpointer_pool = ConnectionPool(
                db_url,
                min_size=settings.DB_POOL_MIN_SIZE,
                max_size=settings.DB_POOL_MAX_SIZE,
                timeout=settings.DB_POOL_TIMEOUT_SECONDS,
                check=getattr(ConnectionPool, "check_connection", None),
                max_idle=300.0,
                max_lifetime=3600.0,
                kwargs={"row_factory": dict_row},
                open=True,
            )
            saver = PostgresSaver(checkpointer_pool)
            pg_checkpointer = PostgresCheckpointer(saver, checkpointer_pool)
            logger.info("PostgresSaver checkpointer successfully initialized with connection pool health checks.")
            return pg_checkpointer
        except Exception as exc:
            if not is_dev:
                raise RuntimeError(
                    f"Production/Non-dev startup failed: PostgreSQL checkpointer initialization error: {exc}"
                )
            logger.warning(f"PostgreSQL connection failed ({exc}). Falling back to MemorySaver for development.")

    if not is_dev:
        if db_url:
            raise RuntimeError(
                "Production startup failed: PostgreSQL checkpointer initialization failed."
            )
        logger.warning(
            "DATABASE_URL not configured in production mode. "
            "Falling back to MemorySaver (thread state will not persist across container restarts)."
        )

    return MemorySaver() if MemorySaver else None


def close_checkpointer():
    global checkpointer_pool
    if checkpointer_pool is not None:
        try:
            checkpointer_pool.close()
            logger.info("checkpointer_pool connection pool closed.")
        except Exception as exc:
            logger.warning(f"Error closing checkpointer_pool: {exc}")
        checkpointer_pool = None


checkpointer = initialize_checkpointer()
