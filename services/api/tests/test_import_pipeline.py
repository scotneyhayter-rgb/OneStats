"""Phase 8, Stage 8.3 — end-to-end generic import through the one pipeline.

A CSV is parsed and normalised by the CSV adapter, staged by the generic stager, and promoted by the
shared source-agnostic promoter — creating teams and matches under the CSV source, idempotent on
re-import, with preview persisting nothing and everything confined to the workspace. Rolled back;
skipped without a live DB.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain.importing import pipeline
from onestats.domain.importing.adapters.csv_scorecard import CsvScorecardAdapter

settings = get_settings()
pytestmark = pytest.mark.skipif(not settings.db_configured, reason="no live database credential configured")
ACTOR = "11111111-1111-1111-1111-111111111111"

CSV = (
    "Date,HomeTeam,AwayTeam,Competition,Grade,Venue,Result,Format,Round\n"
    "2024-01-06,Alpha CC,Beta CC,Saturday League,A Grade,Alpha Oval,Home win,One-day,1\n"
    "2024-01-13,Beta CC,Alpha CC,Saturday League,A Grade,Beta Park,Away win,One-day,2\n"
)


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
    conn.execute(text("INSERT INTO app_user(id, username) VALUES (:a, :u) ON CONFLICT (id) DO NOTHING"),
                 {"a": ACTOR, "u": f"actor-{name}"})
    set_workspace(conn, wid)
    return wid


def _dataset():
    a = CsvScorecardAdapter()
    return a.normalize(a.parse(CSV))


def test_csv_imports_end_to_end_under_one_pipeline(conn):
    wid = _ws(conn, "PIPE CSV")
    out = pipeline.import_dataset(conn, wid, ACTOR, dataset=_dataset(), commit=True, filename="fixtures.csv")
    assert out["committed"] is True and out["source_system"] == "csv_scorecard"
    assert out["created"]["team"] == 2 and out["created"]["match"] == 2
    assert out["created"]["club"] == 2 and out["created"]["venue"] == 2 and out["created"]["division"] == 1

    # matches exist under the CSV source, each with two sides and the recorded date
    rows = conn.execute(text("SELECT id, match_date FROM match WHERE source_system = 'csv_scorecard' ORDER BY match_date")).mappings().all()
    assert len(rows) == 2 and rows[0]["match_date"].isoformat() == "2024-01-06"
    for r in rows:
        assert conn.execute(text("SELECT count(*) FROM match_team WHERE match_id = :m"), {"m": r["id"]}).scalar_one() == 2
    # imported matches are draft — never auto-approved, so they feed no official stats yet
    assert conn.execute(text("SELECT count(*) FROM match WHERE source_system='csv_scorecard' AND approval_status <> 'draft'")).scalar_one() == 0


def test_reimport_is_idempotent(conn):
    wid = _ws(conn, "PIPE CSV IDEM")
    pipeline.import_dataset(conn, wid, ACTOR, dataset=_dataset(), commit=True)
    teams_before = conn.execute(text("SELECT count(*) FROM team")).scalar_one()
    matches_before = conn.execute(text("SELECT count(*) FROM match")).scalar_one()
    out = pipeline.import_dataset(conn, wid, ACTOR, dataset=_dataset(), commit=True)
    assert out["matched"]["team"] == 2 and out["matched"]["match"] == 2
    assert conn.execute(text("SELECT count(*) FROM team")).scalar_one() == teams_before
    assert conn.execute(text("SELECT count(*) FROM match")).scalar_one() == matches_before


def test_preview_persists_nothing(conn):
    wid = _ws(conn, "PIPE CSV PREVIEW")
    out = pipeline.import_dataset(conn, wid, ACTOR, dataset=_dataset(), commit=False)
    assert out["committed"] is False and "created" not in out
    assert out["counts"]["matches"] == 2   # the preview reports what WOULD import
    assert conn.execute(text("SELECT count(*) FROM match")).scalar_one() == 0   # but nothing persisted


def test_workspace_isolation(conn):
    wid_a = _ws(conn, "PIPE ISO A")
    pipeline.import_dataset(conn, wid_a, ACTOR, dataset=_dataset(), commit=True)
    assert conn.execute(text("SELECT count(*) FROM match")).scalar_one() == 2
    wid_b = conn.execute(text("INSERT INTO workspace(name,type) VALUES ('PIPE ISO B','club') RETURNING id")).scalar_one()
    set_workspace(conn, wid_b)
    assert conn.execute(text("SELECT count(*) FROM match")).scalar_one() == 0   # B sees none of A's import
