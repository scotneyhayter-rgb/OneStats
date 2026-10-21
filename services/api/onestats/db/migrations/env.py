"""Alembic environment — resolves the DB URL from application settings (env/.env).

If no credential is configured, offline/online migrations raise a clear error instead of
attempting to connect with no password.
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool

from onestats.core.config import get_settings
from onestats.db.base import Base

config = context.config
target_metadata = Base.metadata


def _database_url() -> str:
    url = get_settings().database_url
    if not url:
        raise RuntimeError(
            "No database credential configured. Set ONESTATS_DB_PASSWORD (or "
            "ONESTATS_DB_URL) in the environment/.env before running migrations."
        )
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = _database_url()
    connectable = engine_from_config(
        section, prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
