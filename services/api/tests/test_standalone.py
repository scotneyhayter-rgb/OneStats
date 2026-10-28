"""Standalone launcher + backup helpers (pure logic; no DB, no subprocess)."""

from __future__ import annotations

import os
from pathlib import Path

from onestats.core.config import Settings
from onestats.domain import backups
from onestats.standalone import launcher


def test_data_dir_prefers_explicit_override(monkeypatch, tmp_path):
    monkeypatch.setenv("ONESTATS_DATA_DIR", str(tmp_path / "od"))
    assert launcher.data_dir() == Path(str(tmp_path / "od"))


def test_data_dir_falls_back_to_localappdata(monkeypatch, tmp_path):
    monkeypatch.delenv("ONESTATS_DATA_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert launcher.data_dir() == Path(str(tmp_path)) / "OneStats"


def test_bind_host_loopback_by_default_network_only_when_set(monkeypatch):
    """The backend binds loopback unless ONESTATS_BIND_HOST is explicitly set (server mode over a VPN)."""
    monkeypatch.delenv("ONESTATS_BIND_HOST", raising=False)
    assert launcher.resolve_bind_host() == launcher.LOOPBACK_HOST
    monkeypatch.setenv("ONESTATS_BIND_HOST", "   ")          # blank -> still loopback
    assert launcher.resolve_bind_host() == launcher.LOOPBACK_HOST
    monkeypatch.setenv("ONESTATS_BIND_HOST", "0.0.0.0")      # explicit -> network
    assert launcher.resolve_bind_host() == "0.0.0.0"


def test_load_config_sets_but_never_overrides(monkeypatch, tmp_path):
    cfg = tmp_path / "onestats.env"
    cfg.write_text('# comment\nONESTATS_DB_NAME=from_file\nONESTATS_DB_USER="quoted_user"\n', encoding="utf-8")
    monkeypatch.setenv("ONESTATS_DB_NAME", "from_env")   # pre-set: must win
    monkeypatch.delenv("ONESTATS_DB_USER", raising=False)
    launcher.load_config(tmp_path)
    assert os.environ["ONESTATS_DB_NAME"] == "from_env"   # not overridden
    assert os.environ["ONESTATS_DB_USER"] == "quoted_user"  # loaded, quotes stripped


def test_conn_parts_parses_runtime_url():
    s = Settings(env="test", db_host="localhost", db_port=5432, db_name="onestats",
                 db_user="onestats_app", db_password="secret", _env_file=None)
    parts = backups._conn_parts(s)
    assert parts["host"] == "localhost"
    assert parts["port"] == "5432"
    assert parts["dbname"] == "onestats"
    assert parts["user"] == "onestats_app"
    assert parts["password"] == "secret"


def test_dump_identity_uses_superuser_when_configured(monkeypatch):
    s = Settings(env="test", db_password="apppw", db_user="onestats_app", _env_file=None)
    parts = backups._conn_parts(s)
    monkeypatch.delenv("ONESTATS_PG_SUPERUSER_PASSWORD", raising=False)
    assert backups._dump_identity(s, parts) == ("onestats_app", "apppw")  # no superuser → app role
    monkeypatch.setenv("ONESTATS_PG_SUPERUSER_PASSWORD", "supw")
    assert backups._dump_identity(s, parts) == ("postgres", "supw")       # default superuser name
    monkeypatch.setenv("ONESTATS_PG_SUPERUSER", "pgadmin")
    assert backups._dump_identity(s, parts) == ("pgadmin", "supw")
