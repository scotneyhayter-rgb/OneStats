"""Auth/setup endpoint wiring tests (no live DB; uses the no-credential test client)."""

from __future__ import annotations


def test_me_requires_bearer_token(client):
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "http_error"


def test_setup_status_needs_database(client):
    # The test client has no DB configured -> 503, proving the route is wired.
    resp = client.get("/api/v1/setup/status")
    assert resp.status_code == 503


def test_login_validates_and_needs_database(client):
    resp = client.post("/api/v1/auth/login", json={"username": "a", "password": "b"})
    assert resp.status_code == 503  # wired; DB unavailable in tests
    # missing fields -> 422 validation
    assert client.post("/api/v1/auth/login", json={}).status_code == 422
