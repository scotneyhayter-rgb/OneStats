"""Phase 12, Stage 12.17 — saved Report Builder configurations. Rolled back; skipped without a live DB."""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain.stats import saved_reports

settings = get_settings()
pytestmark = pytest.mark.skipif(not settings.db_configured, reason="no live database credential configured")
OWNER = "11111111-1111-1111-1111-111111111111"
OTHER = "22222222-2222-2222-2222-222222222222"


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
    for a, u in ((OWNER, "owner"), (OTHER, "other")):
        conn.execute(text("INSERT INTO app_user(id, username) VALUES (:a, :u) ON CONFLICT (id) DO NOTHING"),
                     {"a": a, "u": f"{u}-{name}"})
    set_workspace(conn, wid)
    return wid


def test_crud_and_reopen(conn):
    wid = _ws(conn, "SR")
    r = saved_reports.create(conn, wid, OWNER, name="Top Run Scorers", report="batting",
                             config={"competition_id": None, "min_runs": 500, "order_by": "runs"})
    assert r["report"] == "batting" and r["config"]["min_runs"] == 500
    # reopen (get) returns the same definition
    assert saved_reports.get(conn, r["id"])["name"] == "Top Run Scorers"
    # edit
    upd = saved_reports.update(conn, wid, OWNER, r["id"], config={"min_runs": 1000})
    assert upd["config"]["min_runs"] == 1000
    # duplicate name for same owner rejected
    with pytest.raises(ValueError, match="name_exists"):
        saved_reports.create(conn, wid, OWNER, name="Top Run Scorers", report="batting")
    # delete
    assert saved_reports.delete(conn, wid, OWNER, r["id"]) is True
    assert saved_reports.get(conn, r["id"]) is None


def test_sharing_and_ownership(conn):
    wid = _ws(conn, "SR SHARE")
    mine = saved_reports.create(conn, wid, OWNER, name="Private", report="bowling")
    shared = saved_reports.create(conn, wid, OWNER, name="Club Bowling", report="bowling", shared=True)
    # OTHER sees only the shared one, not the private one
    other_list = {r["name"] for r in saved_reports.list_reports(conn, wid, OTHER)}
    assert "Club Bowling" in other_list and "Private" not in other_list
    # OTHER cannot edit or delete someone else's report
    with pytest.raises(ValueError, match="not_owner"):
        saved_reports.update(conn, wid, OTHER, shared["id"], name="Hijacked")
    with pytest.raises(ValueError, match="not_owner"):
        saved_reports.delete(conn, wid, OTHER, mine["id"])
