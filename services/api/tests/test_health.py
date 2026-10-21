from __future__ import annotations

from onestats import __version__


def test_health_liveness(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["version"] == __version__
    assert body["env"] == "test"


def test_health_db_reports_not_configured_without_credential(client):
    resp = client.get("/api/v1/health/db")
    assert resp.status_code == 200
    body = resp.json()
    assert body["database_configured"] is False
    assert body["database_connected"] is False
    assert "not configured" in body["detail"]


def test_root(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["version"] == __version__


def test_unknown_route_returns_error_envelope(client):
    resp = client.get("/api/v1/does-not-exist")
    assert resp.status_code == 404
    assert "error" in resp.json()
    assert resp.json()["error"]["code"] == "http_error"
