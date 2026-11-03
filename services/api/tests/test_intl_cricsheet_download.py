"""Cricsheet download + import orchestrator — bundle iteration, secure fetch, logging, idempotency.

DB-backed where it imports; the fetch path is exercised offline via an injected httpx MockTransport and
resolver (no network). Proves: a zip of match JSONs is iterated (README/invalid handled), each match is
imported with an honest log row, a re-run of unchanged files is skipped, a non-allow-listed host is
refused before any request, and the secure fetch path returns the bundle bytes.
"""
from __future__ import annotations

import io
import json
import zipfile

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain.intl import cricsheet_download as dl

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


def _match_doc(ref_teams):
    a, b = ref_teams
    return {
        "info": {"match_type": "ODI", "gender": "male", "balls_per_over": 6, "dates": ["2024-02-01"],
                 "teams": [a, b], "venue": "Eden", "outcome": {"winner": a, "by": {"runs": 5}},
                 "players": {a: ["P One"], b: ["P Two"]}, "registry": {"people": {"P One": "r1", "P Two": "r2"}}},
        "innings": [{"team": a, "overs": [{"over": 0, "deliveries": [
            {"batter": "P One", "bowler": "P Two", "runs": {"batter": 4, "extras": 0, "total": 4}},
        ]}]}],
    }


def _zip_bytes():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("README.txt", "cricsheet bundle")
        zf.writestr("111.json", json.dumps(_match_doc(("India", "Australia"))))
        zf.writestr("222.json", json.dumps(_match_doc(("England", "Pakistan"))))
        zf.writestr("333.json", "{not valid json")
    return buf.getvalue()


def _ws(conn):
    wid = conn.execute(text("INSERT INTO workspace(name, type) VALUES ('CS DL','international') RETURNING id")).scalar_one()
    conn.execute(text("INSERT INTO app_user(id, username) VALUES (:a,'dl') ON CONFLICT (id) DO NOTHING"), {"a": ACTOR})
    set_workspace(conn, wid)
    return wid


def test_iter_bundle_skips_readme_and_flags_bad_json():
    refs = {ref: doc for ref, _b, doc in dl.iter_bundle(_zip_bytes())}
    assert set(refs) == {"111", "222", "333"}            # README.txt ignored
    assert refs["333"].get("__invalid_json__") is True   # malformed entry flagged, not crashing


def test_import_bundle_logs_each_match_then_skips_unchanged(conn):
    wid = _ws(conn)
    out = dl.import_matches(conn, wid, ACTOR, dl.iter_bundle(_zip_bytes()))
    assert out["processed"] == 3
    assert out["awaiting_verification"] == 2 and out["failed"] == 1   # two good matches, one bad json
    # honest log rows
    rows = {r["source_ref"]: r["status"] for r in conn.execute(text(
        "SELECT source_ref, status FROM cricsheet_import_log WHERE workspace_id=:w"), {"w": wid}).mappings()}
    assert rows == {"111": "awaiting_verification", "222": "awaiting_verification", "333": "failed"}
    assert dl.summary(conn, wid) == {"awaiting_verification": 2, "skipped": 0, "failed": 1, "total": 3}

    # re-run: unchanged files are skipped (same checksum), the bad one still fails — no duplicates
    out2 = dl.import_matches(conn, wid, ACTOR, dl.iter_bundle(_zip_bytes()))
    assert out2["skipped"] == 2 and out2["failed"] == 1
    n = conn.execute(text("SELECT count(*) FROM match WHERE workspace_id=:w AND source_system='cricsheet'"),
                     {"w": wid}).scalar_one()
    assert n == 2                                         # still exactly two matches


def test_non_mens_match_is_excluded_not_failed(conn):
    # the shared Cricsheet T20I bundle also carries women's matches; those are EXCLUDED (skipped),
    # not counted as import failures (that keeps the error list for genuine problems).
    wid = _ws(conn)
    female = {"info": {"match_type": "IT20", "gender": "female", "teams": ["X", "Y"]}, "innings": []}
    out = dl.import_one(conn, wid, ACTOR, "fem1", b"{}", female)
    assert out == "skipped"
    row = conn.execute(text("SELECT status, detail FROM cricsheet_import_log WHERE workspace_id=:w AND source_ref='fem1'"),
                       {"w": wid}).mappings().one()
    assert row["status"] == "skipped" and "not a men's international" in row["detail"]


def test_bundle_urls_use_the_published_cricsheet_names():
    # men's international T20s are published as "it20s_json.zip" (NOT "t20is") — verified live
    assert dl.bundle_url("test").endswith("/tests_json.zip")
    assert dl.bundle_url("odi").endswith("/odis_json.zip")
    assert dl.bundle_url("t20i").endswith("/it20s_json.zip")


def test_fetch_bundle_refuses_non_allowlisted_host():
    with pytest.raises(ValueError):
        dl.bundle_url("firstclass")                       # not a recognised format
    fetcher = dl.make_fetcher(resolver=lambda h: ["93.184.216.34"], respect_robots=False)
    with pytest.raises(ValueError, match="host_not_allowed"):
        dl.fetch_bundle("test", fetcher=fetcher, base_url="https://evil.example.com/downloads/")


def test_secure_fetch_path_returns_bundle_bytes():
    import httpx
    zb = _zip_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        assert "cricsheet.org" in str(request.url)        # only the allow-listed host is contacted
        return httpx.Response(200, content=zb, headers={"content-type": "application/zip"})

    fetcher = dl.make_fetcher(transport=httpx.MockTransport(handler),
                              resolver=lambda h: ["93.184.216.34"], respect_robots=False)
    res = dl.fetch_bundle("odi", fetcher=fetcher)
    assert res.ok and res.content == zb
    # the fetched bytes round-trip through the iterator
    assert {ref for ref, _b, _d in dl.iter_bundle(res.content)} == {"111", "222", "333"}
