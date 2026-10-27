"""Live people & player-identity tests (Phase 5, Stage 1).

Rolled back in a single transaction (no data persists); skipped without a live DB. Runs as the
least-privilege ``onestats_app`` role under FORCE RLS. Covers the eight Stage 1 verification
points: unique identities, multiple roles per person, historical names + unknown data, source
identity preservation, workspace isolation, permissions + audit, protection against incorrect
identity matching (D Walker / A Bonner), and junior-privacy protection.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import people, permissions

settings = get_settings()
pytestmark = pytest.mark.skipif(
    not settings.db_configured, reason="no live database credential configured"
)

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


# 1. unique identities + 2. multiple roles ---------------------------------


def test_create_person_with_multiple_roles(conn):
    wid = _ws(conn, "PPL WS1")
    pid = people.create_person(conn, wid, ACTOR, display_name="Scotney Hayter",
                               roles=["player", "captain", "administrator"])
    d = people.detail(conn, pid)
    assert d["display_name"] == "Scotney Hayter"
    assert set(d["roles"]) == {"player", "captain", "administrator"}
    # roles are idempotent; one more role can be added
    assert people.add_role(conn, wid, ACTOR, pid, "player")["created"] is False
    people.add_role(conn, wid, ACTOR, pid, "scorer")
    assert "scorer" in people.list_roles(conn, pid)
    people.remove_role(conn, wid, ACTOR, pid, "scorer")
    assert "scorer" not in people.list_roles(conn, pid)


def test_representing_multiple_clubs_is_one_person(conn):
    """A person is not duplicated for representing different clubs — identity is stable."""
    wid = _ws(conn, "PPL WS1b")
    pid = people.create_person(conn, wid, ACTOR, display_name="Journeyman Jones", roles=["player"])
    # Two external source identities (e.g. two clubs' records) attach to ONE person.
    people.add_source_identity(conn, wid, ACTOR, pid, source_system="cs", source_ref="RHY-50")
    people.add_source_identity(conn, wid, ACTOR, pid, source_system="cs", source_ref="MOY-50")
    assert len(people.list_source_identities(conn, pid)) == 2
    assert conn.execute(text("SELECT count(*) FROM person")).scalar_one() == 1


# 3. historical names + unknown data ---------------------------------------


def test_historical_names_and_unknown_dob(conn):
    wid = _ws(conn, "PPL WS2")
    # Cricket Statz placeholder DOB must become unknown, never a real birth date.
    pid = people.create_person(conn, wid, ACTOR, display_name="B Webb", dob="1700-01-01", dob_precision="exact")
    d = people.detail(conn, pid, include_protected=True)
    assert d["dob"] is None and d["dob_precision"] == "unknown"

    people.add_name(conn, wid, ACTOR, pid, name="B", name_type="initials")
    people.add_name(conn, wid, ACTOR, pid, name="Brian Webb", name_type="alias",
                    valid_from=date(1960, 1, 1), valid_to=date(1979, 12, 31))
    names = {n["name"]: n["name_type"] for n in people.list_names(conn, pid)}
    assert names["B"] == "initials"
    assert "Brian Webb" in names
    assert people.name_as_of(conn, pid, date(1970, 1, 1)) == "Brian Webb"


def test_renaming_preserves_history(conn):
    wid = _ws(conn, "PPL WS2b")
    pid = people.create_person(conn, wid, ACTOR, display_name="Old Name")
    people.update_person(conn, wid, ACTOR, pid, display_name="New Name", name_change_note="marriage")
    names = {n["name"] for n in people.list_names(conn, pid)}
    assert {"Old Name", "New Name"} <= names


# 4. source identity preservation + idempotent -----------------------------


def test_source_identity_idempotent(conn):
    wid = _ws(conn, "PPL WS3")
    pid = people.create_person(conn, wid, ACTOR, display_name="Imported Player",
                               source_system="cricket_statz", source_ref="3555610")
    assert len(people.list_source_identities(conn, pid)) == 1
    again = people.add_source_identity(conn, wid, ACTOR, pid, source_system="cricket_statz", source_ref="3555610")
    assert again["created"] is False
    assert len(people.list_source_identities(conn, pid)) == 1


# 7. protection against incorrect identity matching ------------------------


def test_same_name_people_are_not_merged(conn):
    """Two 'A Bonner' are kept as distinct people; a shared name/initials is only weak evidence
    and never an automatic merge."""
    wid = _ws(conn, "PPL WS4")
    a = people.create_person(conn, wid, ACTOR, display_name="A Bonner",
                             source_system="cs", source_ref="3555610")
    b = people.create_person(conn, wid, ACTOR, display_name="A Bonner",
                             source_system="cs", source_ref="3569462")
    # Two distinct person rows — never auto-merged.
    assert a != b
    assert conn.execute(text("SELECT count(*) FROM person")).scalar_one() == 2
    assert people.get_person(conn, a)["merged_into_id"] is None
    assert people.get_person(conn, b)["merged_into_id"] is None
    # Suggested as a possible duplicate (weak, name-only) — a suggestion, not a merge.
    cands = people.find_duplicate_candidates(conn, a)
    assert any(c["person_id"] == b and c["confidence"] == "weak" for c in cands)


def test_source_ref_maps_to_exactly_one_identity(conn):
    """A source reference identifies exactly one person: attaching the same (system, ref) to a
    second person is idempotent to the first owner and never fractures or auto-links identities.
    Deciding whether two 'D Walker' records are the same person is a Stage 3 administrator
    decision backed by evidence — never automatic."""
    wid = _ws(conn, "PPL WS4b")
    a = people.create_person(conn, wid, ACTOR, display_name="D Walker")
    b = people.create_person(conn, wid, ACTOR, display_name="Darren Walker")
    people.add_source_identity(conn, wid, ACTOR, a, source_system="legacy", source_ref="W-1")
    # The same source ref cannot be duplicated onto another person — it resolves to the first owner.
    res = people.add_source_identity(conn, wid, ACTOR, b, source_system="legacy", source_ref="W-1")
    assert res["created"] is False and str(res["person_id"]) == str(a)
    assert len(people.list_source_identities(conn, b)) == 0
    # Both remain distinct people; no automatic merge occurs.
    assert conn.execute(text("SELECT count(*) FROM person")).scalar_one() == 2


# 8 (junior privacy) --------------------------------------------------------


def test_junior_personal_data_protected_by_default(conn):
    wid = _ws(conn, "PPL WS5")
    pid = people.create_person(conn, wid, ACTOR, display_name="Junior Player", is_junior=True,
                               dob=date(2012, 5, 1), dob_precision="exact", notes="school: X")
    # Default read hides DOB/notes for a junior.
    hidden = people.get_person(conn, pid)
    assert hidden["dob"] is None and hidden["notes"] is None and hidden["protected_fields_hidden"] is True
    # A manager can explicitly request protected data.
    shown = people.get_person(conn, pid, include_protected=True)
    assert shown["dob"] == date(2012, 5, 1) and shown["notes"] == "school: X"


# 5. workspace isolation ----------------------------------------------------


def test_people_isolated_across_workspaces(conn):
    wid_a = _mk_workspace(conn, "PPL ISO A")
    wid_b = _mk_workspace(conn, "PPL ISO B")
    set_workspace(conn, wid_a)
    pid = people.create_person(conn, wid_a, ACTOR, display_name="Only In A")
    set_workspace(conn, wid_b)
    assert people.get_person(conn, pid) is None
    assert people.list_people(conn) == []


def test_list_people_sorted_by_surname(conn):
    wid = _ws(conn, "PPL SORT WS")
    # Deliberately created out of surname order; stored as "Initial Surname" like CricketStatz data.
    for name in ("B Allen", "A Zephyr", "C Barham", "A Allen"):
        people.create_person(conn, wid, ACTOR, display_name=name)
    order = [p["display_name"] for p in people.list_people(conn)]
    assert order == ["A Allen", "B Allen", "C Barham", "A Zephyr"]


# 6. permissions + audit ----------------------------------------------------


def test_person_manage_permission_matrix(conn):
    wid = _ws(conn, "PPL PERM WS")
    admin = _mk_user(conn, "ppl_admin")
    viewer = _mk_user(conn, "ppl_viewer")
    permissions.grant_role(conn, admin, wid, "workspace_admin")
    permissions.grant_role(conn, viewer, wid, "viewer")
    assert "person.manage" in permissions.effective_permissions(conn, admin, wid, False)
    assert "person.manage" not in permissions.effective_permissions(conn, viewer, wid, False)


def test_person_changes_are_audited(conn):
    wid = _ws(conn, "PPL AUDIT WS")
    pid = people.create_person(conn, wid, ACTOR, display_name="Audit Person", roles=["player"])
    people.add_role(conn, wid, ACTOR, pid, "umpire")
    people.add_name(conn, wid, ACTOR, pid, name="A. Person", name_type="alias")
    people.update_person(conn, wid, ACTOR, pid, display_name="Audit Person II")
    actions = conn.execute(
        text("SELECT action FROM audit_log WHERE action LIKE 'person%'")
    ).scalars().all()
    for expected in ("person.create", "person.role.add", "person.name.add", "person.update"):
        assert expected in actions


# invalid inputs ------------------------------------------------------------


def test_invalid_inputs(conn):
    wid = _ws(conn, "PPL INVALID WS")
    with pytest.raises(ValueError, match="missing_name"):
        people.create_person(conn, wid, ACTOR, display_name="   ")
    with pytest.raises(ValueError, match="invalid_role"):
        people.create_person(conn, wid, ACTOR, display_name="X", roles=["banana"])
    pid = people.create_person(conn, wid, ACTOR, display_name="Y")
    with pytest.raises(ValueError, match="invalid_name_type"):
        people.add_name(conn, wid, ACTOR, pid, name="Z", name_type="nickname")
