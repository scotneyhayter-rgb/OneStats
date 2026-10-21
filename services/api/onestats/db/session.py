"""Database engine and connectivity check (least-privilege onestats_app role).

The engine is created lazily from the assembled DATABASE_URL. If no credential is
configured, the engine is simply absent and connectivity checks report "not configured"
rather than failing — the API still starts (health liveness works without a DB).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from onestats.core.config import Settings
from onestats.core.logging import get_logger

log = get_logger("onestats.db")

_engine: Engine | None = None


def get_engine(settings: Settings) -> Engine | None:
    """Return a cached engine, or None if the database is not configured."""
    global _engine
    if _engine is not None:
        return _engine
    url = settings.database_url
    if url is None:
        return None
    _engine = create_engine(url, pool_pre_ping=True, future=True)
    return _engine


@dataclass
class DbStatus:
    configured: bool
    connected: bool
    detail: str


def check_connection(settings: Settings) -> DbStatus:
    """Verify connectivity with a trivial query. Never logs the connection string."""
    engine = get_engine(settings)
    if engine is None:
        return DbStatus(False, False, "database credential not configured")
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return DbStatus(True, True, "ok")
    except Exception as exc:  # noqa: BLE001 - report class only, no credentials
        log.warning("DB connectivity check failed: %s", type(exc).__name__)
        return DbStatus(True, False, f"connection failed: {type(exc).__name__}")
