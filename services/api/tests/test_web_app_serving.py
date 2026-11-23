"""One-origin web-app serving (Phase: web-app move, step 1).

When ``serve_frontend`` is on and a built SPA is present, the backend serves the app at ``/`` with
client-side-routing fallback, while the API, docs and asset paths are never shadowed. Off by default the
JSON root is kept (desktop build / health checks). No DB needed — pure app wiring.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from onestats.core.config import Settings
from onestats.main import create_app

MARKER = "ONESTATS_SPA_ROOT_MARKER"


def _dist(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text(
        f"<!doctype html><html><body><div id=root>{MARKER}</div></body></html>", encoding="utf-8")
    (tmp_path / "assets" / "app.js").write_text("console.log('spa')", encoding="utf-8")
    (tmp_path / "favicon.ico").write_text("icon", encoding="utf-8")
    return tmp_path


def _client(tmp_path, *, serve: bool):
    s = Settings(env="test", db_password=None, _env_file=None,
                 serve_frontend=serve, frontend_dist=str(tmp_path) if serve else None)
    return TestClient(create_app(s))


def test_serves_spa_at_root_and_falls_back_for_client_routes(tmp_path):
    client = _client(_dist(tmp_path), serve=True)
    # root serves the SPA entry point
    r = client.get("/")
    assert r.status_code == 200 and MARKER in r.text
    # a deep client route (no server route) falls back to index.html for client-side routing
    r = client.get("/manage/research")
    assert r.status_code == 200 and MARKER in r.text
    # a real static file is served as itself, not the SPA
    r = client.get("/favicon.ico")
    assert r.status_code == 200 and r.text == "icon"
    r = client.get("/assets/app.js")
    assert r.status_code == 200 and "spa" in r.text


def test_api_and_docs_are_not_shadowed_by_the_spa(tmp_path):
    client = _client(_dist(tmp_path), serve=True)
    # an unknown API path 404s as an API route — it must NOT return the SPA index
    r = client.get("/api/v1/does-not-exist")
    assert r.status_code == 404 and MARKER not in r.text
    # interactive docs still work
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_json_root_kept_when_serving_disabled(tmp_path):
    client = _client(tmp_path, serve=False)
    r = client.get("/")
    assert r.status_code == 200 and r.json()["service"]
    # with no SPA catch-all, a client route is just a 404
    assert client.get("/manage/research").status_code == 404


def test_missing_build_is_safe(tmp_path):
    # serve_frontend on but no index.html present → falls back to the JSON root, never breaks startup
    client = _client(tmp_path / "nonexistent", serve=True)
    r = client.get("/")
    assert r.status_code == 200 and r.json()["service"]
