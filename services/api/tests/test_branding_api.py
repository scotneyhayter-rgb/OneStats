"""Branding endpoint auth-gating tests (no live DB)."""

from __future__ import annotations

_WS = "/api/v1/workspaces/00000000-0000-0000-0000-000000000000/branding"


def test_get_branding_requires_auth(client):
    assert client.get(_WS).status_code == 401


def test_set_branding_requires_auth(client):
    assert client.put(_WS, json={"primary_colour": "#123456"}).status_code == 401


def test_logo_upload_requires_auth(client):
    r = client.post(f"{_WS}/logo", files={"file": ("x.png", b"data", "image/png")})
    assert r.status_code == 401
