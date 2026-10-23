"""Live CricketStatz player/official import tests (Phase 5, Stage 5).

Rolled back in a single transaction (no data persists); skipped without a live DB. Runs as the
least-privilege ``onestats_app`` role under FORCE RLS. Uses a **synthetic** CricketStatz-shaped
fixture (fake ids; never the real export). Covers verbatim staging + sentinels, detection,
administrator review decisions, promotion (new / matched / confirmed-existing / distinct), the
player+official single-person rule, idempotent re-import, rollback/recovery, reconciliation,
isolation, permissions and audit.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import people, people_import, permissions, person_resolution

settings = get_settings()
pytestmark = pytest.mark.skipif(
    not settings.db_configured, reason="no live database credential configured"
)

ACTOR = "11111111-1111-1111-1111-111111111111"

PAYLOAD = {
    "players": [
        {"PlayerID": 3555610, "Firstname": "A", "Lastname": "Bonner", "DOB": "1700-01-01", "MyClub": 26267},
        {"PlayerID": 3569462, "Firstname": "Ashton", "Lastname": "Bonner", "DOB": "1700-01-01", "MyClub": 0},
        {"PlayerID": 100001, "Firstname": "Scotney", "Lastname": "Hayter", "DOB": "1990-05-01", "MyClub": 26267},
        {"PlayerID": 100002, "Firstname": "B", "Lastname": "Webb", "DOB": "", "MyClub": 26267},
    ],
    "officials": [
        {"PlayerID": 900001, "Firstname": "Ulric", "Lastname": "Umpire", "DOB": "1700-01-01"},
        # same source id as a player -> one person with both roles
        {"PlayerID": 100001, "Firstname": "Scotney", "Lastname": "Hayter", "DOB": "1990-05-01"},
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


def _records(conn, bid):
    from onestats.domain import imports
    return imports.list_records(conn, bid)


# ---------------------------------------------- staging + sentinels


def test_stage_preserves_raw_and_normalises_sentinels(conn):
    wid = _ws(conn, "PI WS1")
    res = people_import.stage_people(conn, wid, ACTOR, payload=PAYLOAD, filename="CS.json")
    assert res["counts"] == {"player": 4, "official": 2}
    recs = {(r["entity_type"], r["source_ref"]): r for r in _records(conn, res["batch_id"])}
    bonner = recs[("player", "3555610")]
    assert bonner["raw"]["DOB"] == "1700-01-01"           # original preserved
    assert bonner["normalised"]["dob"] is None            # sentinel -> unknown
    assert bonner["normalised"]["dob_precision"] == "unknown"
    assert bonner["normalised"]["display_name"] == "A Bonner"
    # MyClub 0 / blank DOB -> unknown
    assert recs[("player", "3569462")]["normalised"]["myclub_source_ref"] is None
    assert recs[("player", "100002")]["normalised"]["dob"] is None


# ---------------------------------------------- detection + promotion (new)


def test_detect_and_promote_new_people(conn):
    wid = _ws(conn, "PI WS2")
    bid = people_import.stage_people(conn, wid, ACTOR, payload=PAYLOAD)["batch_id"]
    det = people_import.detect(conn, wid, ACTOR, bid)
    assert det["new"] >= 4  # no pre-existing people
    res = people_import.promote(conn, wid, ACTOR, bid)
    # 5 distinct people (two Bonner + Hayter + Webb + Umpire); Hayter player+official is ONE person
    assert conn.execute(text("SELECT count(*) FROM person")).scalar_one() == 5
    assert res["created"]["player"] + res["created"]["official"] >= 5


def test_player_and_official_same_id_is_one_person_with_both_roles(conn):
    wid = _ws(conn, "PI WS2b")
    bid = people_import.stage_people(conn, wid, ACTOR, payload=PAYLOAD)["batch_id"]
    people_import.detect(conn, wid, ACTOR, bid)
    people_import.promote(conn, wid, ACTOR, bid)
    # the Hayter source_ref 100001 resolves to a single person with player + official roles
    pid = conn.execute(
        text("SELECT person_id FROM person_source_identity WHERE source_ref = '100001'")
    ).scalar_one()
    roles = set(people.list_roles(conn, pid))
    assert {"player", "official"} <= roles
    assert conn.execute(
        text("SELECT count(*) FROM person_source_identity WHERE source_ref = '100001'")
    ).scalar_one() == 1  # not duplicated


def test_two_bonner_import_as_distinct_people(conn):
    wid = _ws(conn, "PI WS2c")
    bid = people_import.stage_people(conn, wid, ACTOR, payload=PAYLOAD)["batch_id"]
    people_import.detect(conn, wid, ACTOR, bid)
    people_import.promote(conn, wid, ACTOR, bid)
    # different source refs -> two distinct people, never auto-merged
    cnt = conn.execute(text("SELECT count(*) FROM person_source_identity WHERE source_ref IN ('3555610','3569462')")).scalar_one()
    assert cnt == 2


# ---------------------------------------------- idempotent re-import


def test_idempotent_reimport_matches_not_duplicates(conn):
    wid = _ws(conn, "PI WS3")
    b1 = people_import.stage_people(conn, wid, ACTOR, payload=PAYLOAD)["batch_id"]
    people_import.detect(conn, wid, ACTOR, b1)
    people_import.promote(conn, wid, ACTOR, b1)
    n = conn.execute(text("SELECT count(*) FROM person")).scalar_one()

    b2 = people_import.stage_people(conn, wid, ACTOR, payload=PAYLOAD)["batch_id"]
    det = people_import.detect(conn, wid, ACTOR, b2)
    assert det["matched"] >= 4  # existing source identities matched
    res = people_import.promote(conn, wid, ACTOR, b2)
    assert res["created"]["player"] == 0 and res["created"]["official"] == 0
    assert conn.execute(text("SELECT count(*) FROM person")).scalar_one() == n  # no duplicates


# ---------------------------------------------- resumable / interrupted promotion


def test_promotion_is_resumable(conn):
    wid = _ws(conn, "PI WS4")
    bid = people_import.stage_people(conn, wid, ACTOR, payload=PAYLOAD)["batch_id"]
    people_import.detect(conn, wid, ACTOR, bid)
    people_import.promote(conn, wid, ACTOR, bid)
    # Simulate interruption: reset one promoted record back to staged, then re-run promote.
    conn.execute(text(
        "UPDATE import_staging_record SET status='staged' WHERE batch_id=:b AND source_ref='100002'"
    ), {"b": bid})
    people_import.promote(conn, wid, ACTOR, bid)
    # re-running completes without creating duplicates (100002 already a person by source ref)
    assert conn.execute(text("SELECT count(*) FROM person")).scalar_one() == 5


# ---------------------------------------------- existing-identity review


def test_possible_existing_routed_to_review_and_confirmed(conn):
    wid = _ws(conn, "PI WS5")
    # pre-existing person with the same name as an incoming import record
    existing = people.create_person(conn, wid, ACTOR, display_name="Scotney Hayter")
    bid = people_import.stage_people(conn, wid, ACTOR, payload={"players": [
        {"PlayerID": 777, "Firstname": "Scotney", "Lastname": "Hayter", "DOB": "1990-05-01"}
    ]})["batch_id"]
    det = people_import.detect(conn, wid, ACTOR, bid)
    assert det["possible_existing"] == 1
    rec = _records(conn, bid)[0]
    assert rec["status"] == "unresolved"
    assert existing is not None and str(existing) in (rec["issues"] or {}).get("candidate_person_ids", [])
    # promote now leaves it untouched (not auto-approved)
    people_import.promote(conn, wid, ACTOR, bid)
    assert conn.execute(text("SELECT count(*) FROM person")).scalar_one() == 1  # only the pre-existing
    # admin confirms it IS the existing person -> promote links + enriches (source ref + role)
    people_import.decide_record(conn, wid, ACTOR, rec["id"], decision="existing", existing_person_id=existing)
    people_import.promote(conn, wid, ACTOR, bid)
    assert conn.execute(text("SELECT count(*) FROM person")).scalar_one() == 1  # still one person
    assert conn.execute(text("SELECT person_id FROM person_source_identity WHERE source_ref='777'")).scalar_one() == existing


def test_distinct_decision_creates_new_and_asserts_distinct(conn):
    wid = _ws(conn, "PI WS5b")
    existing = people.create_person(conn, wid, ACTOR, display_name="A Bonner")
    bid = people_import.stage_people(conn, wid, ACTOR, payload={"players": [
        {"PlayerID": 888, "Firstname": "A", "Lastname": "Bonner"}
    ]})["batch_id"]
    people_import.detect(conn, wid, ACTOR, bid)
    rec = _records(conn, bid)[0]
    people_import.decide_record(conn, wid, ACTOR, rec["id"], decision="distinct")
    people_import.promote(conn, wid, ACTOR, bid)
    new_pid = conn.execute(text("SELECT person_id FROM person_source_identity WHERE source_ref='888'")).scalar_one()
    assert new_pid != existing
    assert person_resolution.are_asserted_distinct(conn, new_pid, existing)


# ---------------------------------------------- rollback / recovery


def test_rollback_removes_created_people_and_recovers(conn):
    wid = _ws(conn, "PI WS6")
    bid = people_import.stage_people(conn, wid, ACTOR, payload=PAYLOAD)["batch_id"]
    people_import.detect(conn, wid, ACTOR, bid)
    people_import.promote(conn, wid, ACTOR, bid)
    assert conn.execute(text("SELECT count(*) FROM person")).scalar_one() == 5
    out = people_import.rollback(conn, wid, ACTOR, bid)
    assert out["persons_removed"] == 5
    assert conn.execute(text("SELECT count(*) FROM person")).scalar_one() == 0
    # records recovered to staged -> can promote again
    people_import.promote(conn, wid, ACTOR, bid)
    assert conn.execute(text("SELECT count(*) FROM person")).scalar_one() == 5


def test_rollback_leaves_linked_existing_people(conn):
    wid = _ws(conn, "PI WS6b")
    existing = people.create_person(conn, wid, ACTOR, display_name="Keeper", source_system="legacy", source_ref="L1")
    # import matches the existing person by confirmed-existing decision
    bid = people_import.stage_people(conn, wid, ACTOR, payload={"players": [
        {"PlayerID": 1234, "Firstname": "Keeper", "Lastname": ""}
    ]})["batch_id"]
    people_import.detect(conn, wid, ACTOR, bid)
    rec = _records(conn, bid)[0]
    people_import.decide_record(conn, wid, ACTOR, rec["id"], decision="existing", existing_person_id=existing)
    people_import.promote(conn, wid, ACTOR, bid)
    people_import.rollback(conn, wid, ACTOR, bid)
    # the pre-existing person is NOT deleted (only batch-created people are)
    assert people.get_person(conn, existing) is not None


# ---------------------------------------------- reconciliation (every record accounted for)


def test_reconciliation_accounts_for_every_record(conn):
    wid = _ws(conn, "PI WS7")
    bid = people_import.stage_people(conn, wid, ACTOR, payload=PAYLOAD)["batch_id"]
    people_import.detect(conn, wid, ACTOR, bid)
    people_import.promote(conn, wid, ACTOR, bid)
    rep = people_import.reconcile(conn, bid)
    assert rep["total_staged"] == 6  # 4 players + 2 officials
    assert rep["accounted_for"] == rep["total_staged"]
    assert rep["promoted"] == 6
    assert rep["source_counts"] == {"player": 4, "official": 2}


# ---------------------------------------------- isolation / permissions / audit


def test_isolation(conn):
    wid_a = _mk_workspace(conn, "PI ISO A")
    wid_b = _mk_workspace(conn, "PI ISO B")
    set_workspace(conn, wid_a)
    bid = people_import.stage_people(conn, wid_a, ACTOR, payload=PAYLOAD)["batch_id"]
    set_workspace(conn, wid_b)
    from onestats.domain import imports
    assert imports.get_batch(conn, bid) is None


def test_permission_and_audit(conn):
    wid = _ws(conn, "PI PERM")
    admin = _mk_user(conn, "pi_admin")
    viewer = _mk_user(conn, "pi_viewer")
    permissions.grant_role(conn, admin, wid, "workspace_admin")
    permissions.grant_role(conn, viewer, wid, "viewer")
    assert "import.manage" in permissions.effective_permissions(conn, admin, wid, False)
    assert "import.manage" not in permissions.effective_permissions(conn, viewer, wid, False)

    bid = people_import.stage_people(conn, wid, ACTOR, payload=PAYLOAD)["batch_id"]
    people_import.detect(conn, wid, ACTOR, bid)
    people_import.promote(conn, wid, ACTOR, bid)
    people_import.rollback(conn, wid, ACTOR, bid)
    actions = conn.execute(
        text("SELECT action FROM audit_log WHERE action LIKE 'people_import%'")
    ).scalars().all()
    for expected in ("people_import.stage", "people_import.detect", "people_import.promote", "people_import.rollback"):
        assert expected in actions


def test_invalid_payload(conn):
    wid = _ws(conn, "PI INVALID")
    with pytest.raises(ValueError, match="no_people_collections"):
        people_import.stage_people(conn, wid, ACTOR, payload={"players": [], "officials": []})
