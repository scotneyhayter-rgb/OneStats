from __future__ import annotations

from onestats.core.config import Settings


def test_database_url_none_without_password():
    s = Settings(db_password=None)
    assert s.db_configured is False
    assert s.database_url is None


def test_database_url_assembled_from_parts():
    s = Settings(db_password="s3cret", db_name="onestats", db_user="onestats_app")
    url = s.database_url
    assert url is not None
    assert url.startswith("postgresql+psycopg://onestats_app:")
    assert "@localhost:5432/onestats" in url
    assert s.db_configured is True


def test_db_url_override_takes_precedence():
    s = Settings(
        db_password="ignored",
        ONESTATS_DB_URL="postgresql+psycopg://u:p@db:5432/x",
    )
    assert s.database_url == "postgresql+psycopg://u:p@db:5432/x"
