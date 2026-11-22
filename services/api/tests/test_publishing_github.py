"""Direct 'Publish to web' GitHub upload (publishing_github).

The GitHub connection is stored write-only (the token is never returned); the push to the Git Data API is
exercised with an httpx MockTransport so no network or real token is involved. Requires a live DB; rolled
back in one transaction.
"""
from __future__ import annotations

import httpx
import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import publishing, publishing_github

settings = get_settings()
pytestmark = pytest.mark.skipif(not settings.db_configured, reason="no live database credential configured")
ACTOR = "11111111-1111-1111-1111-111111111111"


@pytest.fixture
def conn():
    eng = create_engine(settings.database_url, future=True)
    with eng.connect() as c:
        trans = c.begin()
        try:
            yield c
        finally:
            trans.rollback()
    eng.dispose()


def _ws(conn, name):
    wid = conn.execute(text("INSERT INTO workspace(name, type) VALUES (:n,'club') RETURNING id"), {"n": name}).scalar_one()
    conn.execute(text("INSERT INTO app_user(id, username) VALUES (:a, 'ghpub') ON CONFLICT (id) DO NOTHING"), {"a": ACTOR})
    set_workspace(conn, wid)
    return wid


def test_settings_are_write_only_and_token_is_preserved_on_blank(conn):
    wid = _ws(conn, "GH SETTINGS")
    s = publishing_github.set_settings(conn, wid, ACTOR, repo="owner/name", branch="main",
                                       token="secret-token", token_provided=True)
    assert s == {"repo": "owner/name", "branch": "main", "token_set": True}
    assert "token" not in s  # the secret is never returned to the caller/client

    # saving the repo again WITHOUT a token keeps the stored token (blank = keep)
    s2 = publishing_github.set_settings(conn, wid, ACTOR, repo="owner/other", branch="gh-pages",
                                        token=None, token_provided=False)
    assert s2 == {"repo": "owner/other", "branch": "gh-pages", "token_set": True}

    # an explicit empty token clears it
    s3 = publishing_github.set_settings(conn, wid, ACTOR, repo="owner/other", branch="main",
                                        token="", token_provided=True)
    assert s3["token_set"] is False


def test_invalid_repo_is_rejected(conn):
    wid = _ws(conn, "GH BADREPO")
    with pytest.raises(ValueError, match="invalid_repo"):
        publishing_github.set_settings(conn, wid, ACTOR, repo="not-a-repo", branch=None, token=None)


def test_publish_requires_a_configuration(conn):
    wid = _ws(conn, "GH UNCONFIGURED")
    with pytest.raises(ValueError, match="github_not_configured"):
        publishing_github.publish_to_github(conn, wid, ACTOR)  # no network — the guard raises first


def test_publish_pushes_the_site_and_sets_the_public_address(conn):
    wid = _ws(conn, "GH PUBLISH")
    publishing_github.set_settings(conn, wid, ACTOR, repo="owner/name", branch="main",
                                   token="ghp_test", token_provided=True)

    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        p, m = request.url.path, request.method
        seen.append(f"{m} {p}")
        if m == "GET" and p.endswith("/git/ref/heads/main"):
            return httpx.Response(404, json={"message": "Not Found"})  # brand-new empty repo -> first commit
        if m == "POST" and p.endswith("/git/blobs"):
            return httpx.Response(201, json={"sha": "blobsha"})
        if m == "POST" and p.endswith("/git/trees"):
            return httpx.Response(201, json={"sha": "treesha"})
        if m == "POST" and p.endswith("/git/commits"):
            return httpx.Response(201, json={"sha": "commitsha"})
        if m == "POST" and p.endswith("/git/refs"):
            return httpx.Response(201, json={"ref": "refs/heads/main"})
        if m == "GET" and p.endswith("/pages"):
            return httpx.Response(404, json={"message": "Not Found"})
        if m == "POST" and p.endswith("/pages"):
            return httpx.Response(201, json={"html_url": "https://owner.github.io/name/"})
        return httpx.Response(500, json={"message": f"unexpected {m} {p}"})

    res = publishing_github.publish_to_github(conn, wid, ACTOR, transport=httpx.MockTransport(handler))

    assert res["committed"] is True
    assert res["commit"] == "commitsha"
    assert res["files"] >= 3  # at least .nojekyll, README.txt and index.html
    assert res["pages_url"] == "https://owner.github.io/name/"
    # the first commit created the branch via POST /git/refs (no parent), not a PATCH
    assert any(s.startswith("POST") and s.endswith("/git/refs") for s in seen)
    # the public site address is filled in automatically so each report's live link appears
    # (stored canonicalised without the trailing slash by set_public_base_url)
    assert publishing.get_public_base_url(conn, wid) == "https://owner.github.io/name"


def test_pages_build_status_maps_states_and_degrades_gracefully(conn):
    wid = _ws(conn, "GH PAGES")
    # not configured (no repo/token) -> unknown, never raises
    assert publishing_github.pages_build_status(conn, wid)["state"] == "unknown"
    publishing_github.set_settings(conn, wid, ACTOR, repo="owner/name", branch="main",
                                   token="ghp_test", token_provided=True)

    def built(_r): return httpx.Response(200, json={"status": "built", "commit": "abc123"})
    r = publishing_github.pages_build_status(conn, wid, transport=httpx.MockTransport(built))
    assert r["state"] == "built" and r["commit"] == "abc123"

    def building(_r): return httpx.Response(200, json={"status": "building", "commit": "abc123"})
    assert publishing_github.pages_build_status(conn, wid, transport=httpx.MockTransport(building))["state"] == "building"

    def errored(_r): return httpx.Response(200, json={"status": "errored"})
    assert publishing_github.pages_build_status(conn, wid, transport=httpx.MockTransport(errored))["state"] == "errored"

    def not_enabled(_r): return httpx.Response(404, json={"message": "Not Found"})
    assert publishing_github.pages_build_status(conn, wid, transport=httpx.MockTransport(not_enabled))["state"] == "unknown"

    def boom(_r): raise httpx.ConnectError("down")
    assert publishing_github.pages_build_status(conn, wid, transport=httpx.MockTransport(boom))["state"] == "unknown"
