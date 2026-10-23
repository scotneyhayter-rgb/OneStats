"""Workspace/onboarding endpoint auth-gating tests (no live DB)."""

from __future__ import annotations


def test_create_workspace_requires_auth(client):
    r = client.post("/api/v1/workspaces", json={"name": "x", "short_name": "y"})
    assert r.status_code == 401


def test_my_workspaces_requires_auth(client):
    assert client.get("/api/v1/workspaces").status_code == 401


def test_onboarding_start_requires_auth(client):
    assert client.post("/api/v1/onboarding", json={}).status_code == 401


def test_add_member_requires_auth(client):
    r = client.post(
        "/api/v1/workspaces/00000000-0000-0000-0000-000000000000/members",
        json={"user_id": "00000000-0000-0000-0000-000000000000", "role": "viewer"},
    )
    assert r.status_code == 401
