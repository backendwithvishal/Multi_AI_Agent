"""
Alembic Programmatic Migration Helper & Runner

Allows running database migrations programmatically during startup or via CLI scripts.
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from alembic import command
from alembic.config import Config

from tripmate.config.settings import settings
from tripmate.database import get_formatted_db_url

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
ALEMBIC_INI_PATH = ROOT_DIR / "alembic.ini"
MIGRATIONS_DIR = ROOT_DIR / "migrations"


def get_alembic_config(db_url: Optional[str] = None) -> Config:
    """Constructs an Alembic Config object with absolute script and config paths."""
    config = Config(str(ALEMBIC_INI_PATH))
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    
    url = db_url or get_formatted_db_url() or settings.DATABASE_URL
    if url:
        if url.startswith("postgres://"):
            url = "postgresql+psycopg://" + url[len("postgres://"):]
        elif url.startswith("postgresql://") and not url.startswith("postgresql+"):
            url = "postgresql+psycopg://" + url[len("postgresql://"):]
        config.set_main_option("sqlalchemy.url", url)
    return config


def run_migrations_up(revision: str = "head", db_url: Optional[str] = None) -> Dict[str, Any]:
    """Runs database migrations forward to the target revision (defaults to 'head')."""
    try:
        config = get_alembic_config(db_url)
        command.upgrade(config, revision)
        return {
            "success": True,
            "revision": revision,
            "message": f"Successfully upgraded schema to revision '{revision}'",
        }
    except Exception as exc:
        return {
            "success": False,
            "revision": revision,
            "error": str(exc),
        }


def run_migrations_down(revision: str, db_url: Optional[str] = None) -> Dict[str, Any]:
    """Downgrades database schema to the specified revision."""
    try:
        config = get_alembic_config(db_url)
        command.downgrade(config, revision)
        return {
            "success": True,
            "revision": revision,
            "message": f"Successfully downgraded schema to revision '{revision}'",
        }
    except Exception as exc:
        return {
            "success": False,
            "revision": revision,
            "error": str(exc),
        }


def get_migration_history() -> List[str]:
    """Returns a list of available migration revisions."""
    versions_dir = MIGRATIONS_DIR / "versions"
    if not versions_dir.exists():
        return []
    return [
        f.stem for f in versions_dir.glob("*.py")
        if not f.name.startswith("__")
    ]
