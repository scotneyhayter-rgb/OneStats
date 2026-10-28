"""Live Cricket Statz structural-import tests (Phase 4, Stage 6).

Rolled back in a single transaction (no data persists); skipped without a live DB. Runs as the
least-privilege ``onestats_app`` role under FORCE RLS. Uses a **synthetic** Cricket-Statz-shaped
fixture — the real RMCC export is never committed or used in tests. Covers staging, validation,
preview, idempotent re-import, promotion, unknown/unresolved preservation, finals safeguards,
historical-identity preservation, rollback/recovery, isolation, permissions and audit.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
import uuid

from onestats.domain import competitions, imports, permissions

settings = get_settings()
pytestmark = pytest.mark.skipif(
    not settings.db_configured, reason="no live database credential configured"
)

ACTOR = "11111111-1111-1111-1111-111111111111"

# Synthetic payload mirroring the Cricket Statz export shape (fake ids; not the real file).
PAYLOAD = {
    "clubs": [
        {"ClubID": 26267, "Name": "RMCC"},
        {"ClubID": 26299, "Name": "Swifts"},
    ],
    "teams": [
        {"TeamID": 19766, "Name": "Rhymney/Moyston", "ClubID": 26267},
        {"TeamID": 19781, "Name": "Moyston", "ClubID": 26267},
        {"TeamID": 19782, "Name": "Rhymney", "ClubID": 26267},
        {"TeamID": 19769, "Name": "Swifts", "ClubID": 26299},
    ],
    "venues": [
        {"GroundID": 100, "Name": "Victoria Park"},
        {"GroundID": 101, "Name": "?"},  # unknown venue sentinel
    ],
    "divisions": [
        {"GradeID": 9770, "Name": "B Grade"},
        {"GradeID": 9774, "Name": "C Grade"},
        {"GradeID": 9771, "Name": "All Grades"},    # ambiguous -> unresolved
        {"GradeID": 12335, "Name": "GCA A Grade"},  # ambiguous -> unresolved
    ],
    "matches": [
        {"MatchID": 3177394, "HomeTeam": 19769, "AwayTeam": 19766, "DatePlayed": "2026-03-07T13:00:00",
         "Ground": 100, "Grade": 9774, "Result": 1, "round": "SF", "matchtype": 1,
         "homebpoints": 0, "awaybpoints": 0},
        {"MatchID": 3000001, "HomeTeam": 19766, "AwayTeam": 19769, "DatePlayed": "2025-12-01T13:00:00",
         "Ground": 101, "Grade": 9770, "Result": 4, "round": "3", "matchtype": 2},  # Result 4 unresolved
        {"MatchID": 3000002, "HomeTeam": 19766, "AwayTeam": 19781, "DatePlayed": "2024-03-01",
         "Ground": 100, "Grade": 9770, "Result": 2, "round": "GF", "matchtype": 1},
    ],
}


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


def _mk_workspace(conn, name):
    return conn.execute(
        text("INSERT INTO workspace(name, type) VALUES (:n,'club') RETURNING id"), {"n": name}
    ).scalar_one()


def _mk_user(conn, u):
    return conn.execute(text("INSERT INTO app_user(username) VALUES (:u) RETURNING id"), {"u": u}).scalar_one()


def _ws(conn, name):
    wid = _mk_workspace(conn, name)
    set_workspace(conn, wid)
    return wid


def _canon_counts(conn):
    def n(tbl):
        return conn.execute(text(f"SELECT count(*) FROM {tbl}")).scalar_one()
    return {t: n(t) for t in ("organisation", "team", "venue", "grade", "competition", "match")}


# ---------------------------------------------------------------- staging


def test_stage_preserves_raw_and_flags_unknowns(conn):
    wid = _ws(conn, "IMP WS1")
    res = imports.parse_and_stage(conn, wid, ACTOR, payload=PAYLOAD, filename="CS.json")
    assert res["counts"] == {"club": 2, "venue": 2, "division": 4, "team": 4, "match": 3,
                             "innings": 0, "batting_entry": 0, "bowling_entry": 0, "fall_of_wicket": 0}
    bid = res["batch_id"]

    # Unknown venue "?" -> normalised name None, raw preserved verbatim.
    venue_recs = {r["source_ref"]: r for r in imports.list_records(conn, bid, entity_type="venue")}
    assert venue_recs["101"]["normalised"]["name"] is None
    assert venue_recs["101"]["raw"]["Name"] == "?"  # original untouched

    # Every named division becomes a grade verbatim (like clubs/teams/venues) — B/C Grade, the
    # catch-all "All Grades", and the prefixed "GCA A Grade" all stage.
    div = {r["source_ref"]: r for r in imports.list_records(conn, bid, entity_type="division")}
    for ref in ("9770", "9774", "9771", "12335"):
        assert div[ref]["status"] == "staged"

    # Match: Result 4 unresolved; classification always unresolved; round preserved verbatim.
    m = {r["source_ref"]: r for r in imports.list_records(conn, bid, entity_type="match")}
    assert m["3000001"]["normalised"]["result_status"] == "unresolved"
    assert m["3000001"]["normalised"]["result"] == 4  # original value kept
    assert m["3177394"]["normalised"]["result_label"] == "home_win"  # 1 confirmed
    for rec in m.values():
        assert rec["normalised"]["classification_status"] == "unresolved"
    assert m["3000002"]["normalised"]["round"] == "GF"  # verbatim, only a hint


def test_finals_round_divisions_not_promoted_as_grades(conn):
    """A division whose name is really a finals round / classification (or is blank) is never turned
    into a grade — it stays unresolved for admin review. Every other named division becomes a grade."""
    wid = _ws(conn, "IMP GRADES")
    payload = {"divisions": [
        {"GradeID": 1, "Name": "A Grade"},
        {"GradeID": 2, "Name": "Under 16"},
        {"GradeID": 3, "Name": "Grand Final"},
        {"GradeID": 4, "Name": "Semi Final"},
        {"GradeID": 5, "Name": ""},            # blank name
    ]}
    bid = imports.parse_and_stage(conn, wid, ACTOR, payload=payload)["batch_id"]
    div = {r["source_ref"]: r for r in imports.list_records(conn, bid, entity_type="division")}
    assert div["1"]["status"] == "staged" and div["2"]["status"] == "staged"            # real grades
    assert div["3"]["status"] == "unresolved" and div["4"]["status"] == "unresolved"    # finals rounds
    assert div["5"]["status"] == "unresolved"                                           # blank name
    imports.promote_batch(conn, wid, ACTOR, bid)
    names = {r[0] for r in conn.execute(text("SELECT name FROM grade")).all()}
    assert {"A Grade", "Under 16"} <= names
    assert "Grand Final" not in names and "Semi Final" not in names


def test_import_into_named_competition(conn):
    """The user can name the competition at import (the export carries none); imported grades and
    matches land under it, found-or-created by name — not the generic container. Idempotent by name."""
    wid = _ws(conn, "IMP COMP NAME")
    bid = imports.parse_and_stage(conn, wid, ACTOR, payload=PAYLOAD)["batch_id"]
    imports.promote_batch(conn, wid, ACTOR, bid, competition_name="Grampians Cricket Association")
    comp = conn.execute(text("SELECT id FROM competition WHERE name = 'Grampians Cricket Association'")).scalar_one()
    assert conn.execute(text("SELECT count(*) FROM grade WHERE competition_id = :c"), {"c": comp}).scalar_one() == 4
    assert conn.execute(text("SELECT count(*) FROM match WHERE competition_id = :c"), {"c": comp}).scalar_one() == 3
    assert conn.execute(text("SELECT count(*) FROM competition WHERE name = 'Cricket Statz Import'")).scalar_one() == 0
    # re-import under the same name (any case/spacing) reuses the competition — no duplicate
    bid2 = imports.parse_and_stage(conn, wid, ACTOR, payload=PAYLOAD)["batch_id"]
    imports.promote_batch(conn, wid, ACTOR, bid2, competition_name="  grampians   cricket association ")
    assert conn.execute(text("SELECT count(*) FROM competition WHERE workspace_id = :w "
                             "AND lower(name) = lower('Grampians Cricket Association')"), {"w": wid}).scalar_one() == 1


def test_import_into_existing_competition_by_id(conn):
    """An existing competition can be chosen by id; a bad id is rejected."""
    wid = _ws(conn, "IMP COMP ID")
    comp = competitions.create_competition(conn, wid, ACTOR, name="My League")
    bid = imports.parse_and_stage(conn, wid, ACTOR, payload=PAYLOAD)["batch_id"]
    imports.promote_batch(conn, wid, ACTOR, bid, competition_id=comp)
    assert conn.execute(text("SELECT count(*) FROM match WHERE competition_id = :c"), {"c": comp}).scalar_one() == 3
    bid2 = imports.parse_and_stage(conn, wid, ACTOR, payload=PAYLOAD)["batch_id"]
    with pytest.raises(ValueError, match="competition_not_found"):
        imports.promote_batch(conn, wid, ACTOR, bid2, competition_id=uuid.uuid4())


def test_stage_matchtype_labels(conn):
    wid = _ws(conn, "IMP WS1b")
    bid = imports.parse_and_stage(conn, wid, ACTOR, payload=PAYLOAD)["batch_id"]
    m = {r["source_ref"]: r for r in imports.list_records(conn, bid, entity_type="match")}
    assert m["3177394"]["normalised"]["matchtype_label"] == "1 innings per side"
    assert m["3000001"]["normalised"]["matchtype_label"] == "2 innings per side"


# ---------------------------------------------------------------- validate


def test_validate_flags_broken_refs_without_dropping(conn):
    wid = _ws(conn, "IMP WS2")
    bad = {
        "clubs": [{"ClubID": 1, "Name": "A"}],
        "teams": [{"TeamID": 2, "Name": "Orphan", "ClubID": 999}],  # 999 not in clubs
        "matches": [{"MatchID": 3, "HomeTeam": 2, "AwayTeam": 777, "Grade": 888, "Ground": 666,
                     "DatePlayed": "2020-01-01", "Result": 1, "round": "1", "matchtype": 1}],
    }
    bid = imports.parse_and_stage(conn, wid, ACTOR, payload=bad)["batch_id"]
    out = imports.validate_batch(conn, wid, ACTOR, bid)
    assert out["ref_problems"] >= 1
    team = imports.list_records(conn, bid, entity_type="team")[0]
    assert any("club_ref_unresolved" in i for i in (team["issues"] or []))
    # nothing dropped — the orphan team is still present
    assert len(imports.list_records(conn, bid, entity_type="team")) == 1


# ---------------------------------------------------------------- promote


def test_promote_creates_canonical_including_matches(conn):
    """Stage 8: matches are now promoted into canonical ``match`` rows (with linked sides, grade,
    venue and preserved raw result), alongside clubs/teams/venues/grades."""
    wid = _ws(conn, "IMP WS3")
    before = _canon_counts(conn)
    bid = imports.parse_and_stage(conn, wid, ACTOR, payload=PAYLOAD)["batch_id"]
    res = imports.promote_batch(conn, wid, ACTOR, bid)

    assert res["created"] == {"club": 2, "venue": 2, "team": 4, "division": 4, "match": 3,
                              "innings": 0, "batting_entry": 0, "bowling_entry": 0,
                              "fall_of_wicket": 0, "partnership": 0}
    assert res["status"] == "promoted"  # every named division is a grade now; nothing left unresolved
    after = _canon_counts(conn)
    assert after["organisation"] - before["organisation"] == 2
    assert after["team"] - before["team"] == 4
    assert after["venue"] - before["venue"] == 2
    assert after["grade"] - before["grade"] == 4  # all four named divisions promoted verbatim
    assert after["competition"] - before["competition"] == 1  # one import container
    assert after["match"] - before["match"] == 3

    # every match row promoted; none left staged
    for rec in imports.list_records(conn, bid, entity_type="match"):
        assert rec["status"] == "promoted" and rec["resolution"] == "new"
    # Every named division became a grade; none left unresolved (no finals-round/blank names here).
    unresolved = imports.list_records(conn, bid, entity_type="division", status="unresolved")
    assert len(unresolved) == 0

    # the away-win match (3000002, Result 2) records the away side as winner; the raw code is kept
    m = conn.execute(text(
        "SELECT result_type, result_raw, won_by_team_id, classification, classification_verified, "
        "match_date, round FROM match WHERE source_ref = '3000002'")).mappings().one()
    away_team_id = conn.execute(text("SELECT id FROM team WHERE source_ref = '19781'")).scalar_one()
    assert m["result_type"] == "away_win" and m["result_raw"] == "2" and m["won_by_team_id"] == away_team_id
    # round is preserved verbatim but NEVER classifies the match
    assert m["round"] == "GF" and m["classification"] == "unclassified" and m["classification_verified"] is False
    # the Result-4 match stays unknown (not evidence-verified) — never guessed
    assert conn.execute(text("SELECT result_type FROM match WHERE source_ref = '3000001'")).scalar_one() == "unknown"


def test_idempotent_reimport_matches_not_duplicates(conn):
    wid = _ws(conn, "IMP WS4")
    b1 = imports.parse_and_stage(conn, wid, ACTOR, payload=PAYLOAD)["batch_id"]
    imports.promote_batch(conn, wid, ACTOR, b1)
    mid = _canon_counts(conn)

    # Re-import the same file as a new batch, then promote.
    b2 = imports.parse_and_stage(conn, wid, ACTOR, payload=PAYLOAD)["batch_id"]
    res = imports.promote_batch(conn, wid, ACTOR, b2)
    sc0 = {"innings": 0, "batting_entry": 0, "bowling_entry": 0, "fall_of_wicket": 0, "partnership": 0}
    assert res["created"] == {"club": 0, "venue": 0, "team": 0, "division": 0, "match": 0, **sc0}
    assert res["matched"] == {"club": 2, "venue": 2, "team": 4, "division": 4, "match": 3, **sc0}
    assert _canon_counts(conn) == mid  # no duplicate canonical rows (matches included)


def test_historical_identities_stay_distinct(conn):
    """The three RMCC teams import as three distinct teams — never merged on name."""
    wid = _ws(conn, "IMP WS5")
    bid = imports.parse_and_stage(conn, wid, ACTOR, payload=PAYLOAD)["batch_id"]
    imports.promote_batch(conn, wid, ACTOR, bid)
    rows = conn.execute(
        text("SELECT source_ref, name FROM team ORDER BY source_ref")
    ).mappings().all()
    by_ref = {r["source_ref"]: r["name"] for r in rows}
    assert {"19766", "19781", "19782"} <= set(by_ref)
    assert by_ref["19766"] == "Rhymney/Moyston"
    assert by_ref["19781"] == "Moyston"
    assert by_ref["19782"] == "Rhymney"
    # four distinct teams, none merged
    assert conn.execute(text("SELECT count(*) FROM team WHERE merged_into_id IS NULL")).scalar_one() == 4


# ---------------------------------------------------------------- rollback / recovery


def test_rollback_removes_only_batch_created_rows_and_recovers(conn):
    wid = _ws(conn, "IMP WS6")
    before = _canon_counts(conn)
    bid = imports.parse_and_stage(conn, wid, ACTOR, payload=PAYLOAD)["batch_id"]
    imports.promote_batch(conn, wid, ACTOR, bid)
    assert _canon_counts(conn)["team"] - before["team"] == 4

    out = imports.rollback_batch(conn, wid, ACTOR, bid)
    assert out["removed"] == {"match": 3, "team": 4, "division": 4, "venue": 2, "club": 2,
                              "innings": 0, "batting_entry": 0, "bowling_entry": 0, "fall_of_wicket": 0}
    # canonical returns to the pre-promotion baseline (competition container left in place)
    after = _canon_counts(conn)
    assert after["organisation"] == before["organisation"]
    assert after["team"] == before["team"]
    assert after["venue"] == before["venue"]
    assert after["grade"] == before["grade"]
    assert after["match"] == before["match"]  # imported matches removed too
    # staging records are recovered to 'staged' and can be promoted again
    assert all(r["status"] == "staged" for r in imports.list_records(conn, bid, entity_type="club"))
    res2 = imports.promote_batch(conn, wid, ACTOR, bid)
    assert res2["created"]["club"] == 2


def test_cancel_blocked_after_promotion(conn):
    wid = _ws(conn, "IMP WS6b")
    bid = imports.parse_and_stage(conn, wid, ACTOR, payload=PAYLOAD)["batch_id"]
    imports.promote_batch(conn, wid, ACTOR, bid)
    with pytest.raises(ValueError, match="batch_has_promoted_rows_use_rollback"):
        imports.cancel_batch(conn, wid, ACTOR, bid)


def test_cancel_before_promotion(conn):
    wid = _ws(conn, "IMP WS6c")
    bid = imports.parse_and_stage(conn, wid, ACTOR, payload=PAYLOAD)["batch_id"]
    assert imports.cancel_batch(conn, wid, ACTOR, bid)["status"] == "cancelled"


# ---------------------------------------------------------------- isolation


def test_batches_isolated_across_workspaces(conn):
    wid_a = _mk_workspace(conn, "IMP ISO A")
    wid_b = _mk_workspace(conn, "IMP ISO B")
    set_workspace(conn, wid_a)
    bid = imports.parse_and_stage(conn, wid_a, ACTOR, payload=PAYLOAD)["batch_id"]
    set_workspace(conn, wid_b)
    assert imports.get_batch(conn, bid) is None
    assert imports.list_batches(conn) == []


# ---------------------------------------------------------------- permissions


def test_import_manage_permission_matrix(conn):
    wid = _ws(conn, "IMP PERM WS")
    admin = _mk_user(conn, "imp_admin")
    viewer = _mk_user(conn, "imp_viewer")
    permissions.grant_role(conn, admin, wid, "workspace_admin")
    permissions.grant_role(conn, viewer, wid, "viewer")
    assert "import.manage" in permissions.effective_permissions(conn, admin, wid, False)
    assert "import.manage" not in permissions.effective_permissions(conn, viewer, wid, False)


# ---------------------------------------------------------------- audit


def test_import_lifecycle_is_audited(conn):
    wid = _ws(conn, "IMP AUDIT WS")
    bid = imports.parse_and_stage(conn, wid, ACTOR, payload=PAYLOAD)["batch_id"]
    imports.validate_batch(conn, wid, ACTOR, bid)
    imports.promote_batch(conn, wid, ACTOR, bid)
    imports.rollback_batch(conn, wid, ACTOR, bid)
    actions = conn.execute(
        text("SELECT action FROM audit_log WHERE action LIKE 'import%'")
    ).scalars().all()
    for expected in ("import.stage", "import.validate", "import.promote", "import.rollback"):
        assert expected in actions
