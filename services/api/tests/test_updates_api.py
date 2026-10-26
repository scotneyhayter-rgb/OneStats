"""Update-system endpoint auth-gating + domain helpers (no live DB).

Full version/compatibility rules are covered in test_version.py; here we assert the HTTP surface is
authenticated/authorised and that the pure domain helpers behave. DB-backed behaviour (maintenance
gate, capability content, pre-checks) is exercised against the dev database and in manual acceptance
(UP-14..UP-22).
"""

from __future__ import annotations

from onestats.core.config import Settings
from onestats.domain import updates


def test_capability_requires_auth(client):
    assert client.get("/api/v1/capability").status_code == 401


def test_compatibility_requires_auth(client):
    assert client.get("/api/v1/updates/compatibility?desktop_version=1.0.0").status_code == 401


def test_system_status_requires_auth(client):
    assert client.get("/api/v1/system/updates/status").status_code == 401


def test_history_requires_auth(client):
    assert client.get("/api/v1/updates/history").status_code == 401


def test_pre_check_requires_auth(client):
    assert client.post("/api/v1/system/updates/pre-check").status_code == 401


def test_maintenance_requires_auth(client):
    assert client.post("/api/v1/system/updates/maintenance", json={"on": True}).status_code == 401


def test_schema_level_parsing():
    assert updates._schema_level("0058_update_system") == 58
    assert updates._schema_level("0001_foundation") == 1
    assert updates._schema_level(None) is None
    assert updates._schema_level("no_digits") is None


def test_backup_readiness_reports_writable_destination(tmp_path):
    s = Settings(env="test", db_password=None, backup_dir=str(tmp_path / "backups"), _env_file=None)
    r = updates.backup_readiness(s)
    assert r["writable"] is True
    assert r["free_bytes"] is not None and r["free_bytes"] > 0
    assert r["destination"].endswith("backups")
