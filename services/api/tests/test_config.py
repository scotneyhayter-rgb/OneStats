from __future__ import annotations

from onestats.core.config import Settings


def test_database_url_none_without_password():
    s = Settings(db_password=None, _env_file=None)
    assert s.db_configured is False
    assert s.database_url is None


def test_database_url_assembled_from_parts():
    s = Settings(db_password="s3cret", db_name="onestats", db_user="onestats_app", _env_file=None)
    url = s.database_url
    assert url is not None
    assert url.startswith("postgresql+psycopg://onestats_app:")
    assert "@localhost:5432/onestats" in url
    assert s.db_configured is True


def test_db_url_override_takes_precedence():
    s = Settings(
        db_password="ignored",
        ONESTATS_DB_URL="postgresql+psycopg://u:p@db:5432/x",
        _env_file=None,
    )
    assert s.database_url == "postgresql+psycopg://u:p@db:5432/x"


def test_migration_url_uses_migrator_when_set():
    s = Settings(db_password="apppw", migrator_password="migpw", _env_file=None)
    # runtime stays onestats_app; migrations use onestats_migrator
    assert s.database_url.startswith("postgresql+psycopg://onestats_app:")
    assert s.migration_url.startswith("postgresql+psycopg://onestats_migrator:")


def test_migration_url_falls_back_to_runtime():
    s = Settings(db_password="apppw", _env_file=None)  # no migrator password
    assert s.migration_url == s.database_url


def test_migration_url_none_without_any_credential():
    s = Settings(_env_file=None)
    assert s.migration_url is None
