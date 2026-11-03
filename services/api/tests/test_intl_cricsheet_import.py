"""Cricsheet importer — maps a parsed match onto the scorecard tables, idempotently and identity-safe.

DB-backed, rolled back; skipped without a live DB. Proves: a first import creates the match, innings,
batting and bowling with accurate figures and a linked match-index entry; a re-import UPDATES in place
(no duplicate) and resolves the same people via the Cricsheet registry id (stable identity); and an
already-approved scorecard is never overwritten by a re-import.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import matches
from onestats.domain.intl import cricsheet
from onestats.domain.intl import cricsheet_import as imp

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


def _d(batter, bowler, runs, *, extras=None, wicket=None):
    total = runs + sum((extras or {}).values())
    d = {"batter": batter, "bowler": bowler, "non_striker": "NS",
         "runs": {"batter": runs, "extras": sum((extras or {}).values()), "total": total}}
    if extras:
        d["extras"] = extras
    if wicket:
        d["wickets"] = [wicket]
    return d


DOC = {
    "info": {
        "match_type": "Test", "gender": "male", "balls_per_over": 6, "dates": ["2024-01-10"],
        "teams": ["Australia", "England"], "venue": "MCG", "event": {"name": "The Ashes", "match_number": 2},
        "outcome": {"winner": "Australia", "by": {"runs": 100}},
        "players": {"Australia": ["D Warner", "S Smith", "T Head"], "England": ["S Broad", "J Root"]},
        "registry": {"people": {"D Warner": "aa11", "S Broad": "cc33"}},  # Smith/Head/Root have no id
    },
    "innings": [{"team": "Australia", "overs": [{"over": 0, "deliveries": [
        _d("D Warner", "S Broad", 4),
        _d("D Warner", "S Broad", 6),
        _d("D Warner", "S Broad", 0, wicket={"player_out": "D Warner", "kind": "caught", "fielders": [{"name": "J Root"}]}),
        _d("S Smith", "S Broad", 1),
        _d("S Smith", "S Broad", 0),
        _d("T Head", "S Broad", 2),
    ]}]}],
}


def _ws(conn):
    wid = conn.execute(text("INSERT INTO workspace(name, type) VALUES ('CS IMPORT','international') RETURNING id")).scalar_one()
    conn.execute(text("INSERT INTO app_user(id, username) VALUES (:a,'imp') ON CONFLICT (id) DO NOTHING"), {"a": ACTOR})
    set_workspace(conn, wid)
    return wid


def _parsed():
    return cricsheet.parse_match(DOC, source_ref="777001")


def _persons_named(conn, wid, name):
    return conn.execute(text("SELECT count(*) FROM person WHERE workspace_id=:w AND lower(display_name)=lower(:n)"),
                        {"w": wid, "n": name}).scalar_one()


def test_first_import_writes_an_accurate_scorecard(conn):
    wid = _ws(conn)
    out = imp.import_match(conn, wid, ACTOR, _parsed())
    assert out["status"] == "created" and out["innings"] == 1 and out["indexed"] is True
    assert set(out["teams_created"]) == {"Australia", "England"}
    assert out["approved"] is False                                   # not auto-counted to stats

    # Warner's batting landed accurately (10 runs, a four and a six, caught off Broad)
    row = conn.execute(text(
        "SELECT be.runs, be.fours, be.sixes, be.dismissal_type, p2.display_name AS bowler "
        "FROM batting_entry be JOIN person p ON p.id = be.person_id "
        "LEFT JOIN person p2 ON p2.id = be.bowler_person_id "
        "WHERE be.workspace_id=:w AND p.display_name='D Warner'"), {"w": wid}).mappings().one()
    assert row["runs"] == 10 and row["fours"] == 1 and row["sixes"] == 1
    assert row["dismissal_type"] == "caught" and row["bowler"] == "S Broad"
    # Broad's bowling: 1 wicket, runs conceded 13 (4+6+0+1+0+2 off the bat, no extras)
    bw = conn.execute(text(
        "SELECT bo.wickets, bo.runs_conceded FROM bowling_entry bo JOIN person p ON p.id=bo.person_id "
        "WHERE bo.workspace_id=:w AND p.display_name='S Broad'"), {"w": wid}).mappings().one()
    assert bw["wickets"] == 1 and bw["runs_conceded"] == 13
    # match-index entry is linked and imported
    idx = conn.execute(text("SELECT state, source_refs FROM match_index_entry WHERE workspace_id=:w"),
                       {"w": wid}).mappings().one()
    assert idx["state"] == "imported" and idx["source_refs"]["cricsheet"] == "777001"


def test_reimport_updates_in_place_with_stable_identities(conn):
    wid = _ws(conn)
    imp.import_match(conn, wid, ACTOR, _parsed())
    out2 = imp.import_match(conn, wid, ACTOR, _parsed())
    assert out2["status"] == "updated"
    # exactly one match for this source ref — not duplicated
    n = conn.execute(text("SELECT count(*) FROM match WHERE workspace_id=:w AND source_ref='777001'"),
                     {"w": wid}).scalar_one()
    assert n == 1
    # each player still exactly one person (registry id / unique name resolved the same identity)
    for name in ("D Warner", "S Broad", "S Smith", "T Head", "J Root"):
        assert _persons_named(conn, wid, name) == 1
    assert out2["players_created"] == 0                      # nobody re-created on the second pass


def test_fall_of_wickets_and_home_away_unknown_are_recorded(conn):
    wid = _ws(conn)
    first = imp.import_match(conn, wid, ACTOR, _parsed())
    # home/away is unknown for internationals (Cricsheet gives none) -> flagged, not assumed
    assert conn.execute(text("SELECT home_away_known FROM match WHERE id=:m"), {"m": first["match_id"]}).scalar_one() is False
    # one fall of wicket: Warner out at team score 10, on the 3rd legal ball
    fow = conn.execute(text(
        "SELECT f.wicket_number, f.team_score, f.legal_balls, p.display_name "
        "FROM fall_of_wicket f JOIN person p ON p.id=f.dismissed_person_id WHERE f.workspace_id=:w"),
        {"w": wid}).mappings().all()
    assert len(fow) == 1
    assert (fow[0]["wicket_number"], fow[0]["team_score"], fow[0]["legal_balls"], fow[0]["display_name"]) == (1, 10, 3, "D Warner")


def test_registry_less_name_clash_queues_a_review_and_does_not_merge(conn):
    wid = _ws(conn)
    # a pre-existing "S Smith" (Smith has NO registry id in the fixture)
    existing = conn.execute(text(
        "INSERT INTO person(workspace_id, display_name) VALUES (:w,'S Smith') RETURNING id"), {"w": wid}).scalar_one()
    out = imp.import_match(conn, wid, ACTOR, _parsed())
    assert out["identity_reviews_queued"] >= 1
    # the import created a SECOND Smith rather than silently reusing the existing one
    assert _persons_named(conn, wid, "S Smith") == 2
    # a duplicate review now pairs them for a human to resolve
    rev = conn.execute(text(
        "SELECT count(*) FROM person_duplicate_review WHERE workspace_id=:w AND (person_a_id=:e OR person_b_id=:e)"),
        {"w": wid, "e": existing}).scalar_one()
    assert rev == 1


def test_reimport_never_overwrites_a_verified_scorecard(conn):
    wid = _ws(conn)
    first = imp.import_match(conn, wid, ACTOR, _parsed())
    matches.set_approval(conn, wid, ACTOR, first["match_id"], status="approved")
    out = imp.import_match(conn, wid, ACTOR, _parsed())
    assert out["status"] == "skipped_verified" and out["match_id"] == first["match_id"]
    # the approved match is untouched (still approved, still one match)
    status = conn.execute(text("SELECT approval_status FROM match WHERE id=:m"), {"m": first["match_id"]}).scalar_one()
    assert status == "approved"
