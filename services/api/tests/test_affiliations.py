"""Live person-affiliation tests (Phase 5, Stage 2).

Rolled back in a single transaction (no data persists); skipped without a live DB. Runs as the
least-privilege ``onestats_app`` role under FORCE RLS. Covers multi-club careers, concurrent
roles/affiliations, transfers and returns, unknown/approximate periods, the Rhymney/Moyston
reference case (distinct orgs, attribution preserved), affiliation-vs-participation separation,
verification/corrections, isolation, permissions and audit.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import affiliations, people, permissions

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


def _org(conn, wid, name, kind="club"):
    return conn.execute(
        text("INSERT INTO organisation(workspace_id, name, kind) VALUES (:w, :n, :k) RETURNING id"),
        {"w": wid, "n": name, "k": kind},
    ).scalar_one()


def _team(conn, wid, org, name):
    return conn.execute(
        text("INSERT INTO team(workspace_id, organisation_id, name) VALUES (:w, :o, :n) RETURNING id"),
        {"w": wid, "o": org, "n": name},
    ).scalar_one()


def _person(conn, wid, name):
    return people.create_person(conn, wid, ACTOR, display_name=name)


# ---------------------------------------------- multi-club career + transfers/returns


def test_multi_club_career_with_transfer_and_return(conn):
    wid = _ws(conn, "AFF WS1")
    p = _person(conn, wid, "Journeyman")
    club_a = _org(conn, wid, "Club A")
    club_b = _org(conn, wid, "Club B")
    affiliations.create_affiliation(conn, wid, ACTOR, person_id=p, organisation_id=club_a, role="player",
                                    valid_from=date(2000, 10, 1), valid_to=date(2004, 3, 31))
    affiliations.create_affiliation(conn, wid, ACTOR, person_id=p, organisation_id=club_b, role="player",
                                    valid_from=date(2004, 10, 1), valid_to=date(2009, 3, 31))
    affiliations.create_affiliation(conn, wid, ACTOR, person_id=p, organisation_id=club_a, role="player",
                                    valid_from=date(2009, 10, 1))  # returned to former club
    career = affiliations.person_career(conn, p)
    assert len(career) == 3
    assert sum(1 for a in career if a["organisation_id"] == club_a) == 2  # original + return


def test_concurrent_affiliations_and_roles(conn):
    wid = _ws(conn, "AFF WS2")
    p = _person(conn, wid, "Busy Member")
    club = _org(conn, wid, "Club")
    assoc = _org(conn, wid, "Association", kind="association")
    # Concurrent: plays and captains at the club, and is an association official — same period.
    affiliations.create_affiliation(conn, wid, ACTOR, person_id=p, organisation_id=club, role="player",
                                    valid_from=date(2020, 10, 1))
    affiliations.create_affiliation(conn, wid, ACTOR, person_id=p, organisation_id=club, role="captain",
                                    valid_from=date(2020, 10, 1))
    affiliations.create_affiliation(conn, wid, ACTOR, person_id=p, organisation_id=assoc,
                                    role="association_official", valid_from=date(2020, 10, 1))
    active = affiliations.affiliations_as_of(conn, p, date(2021, 1, 1))
    roles = {a["role"] for a in active}
    assert {"player", "captain", "association_official"} <= roles
    assert len(active) == 3  # all concurrent


def test_extensible_role_needs_no_migration(conn):
    wid = _ws(conn, "AFF WS2b")
    p = _person(conn, wid, "Custom Role Person")
    club = _org(conn, wid, "Club")
    # A role outside the standard set is accepted (free text column).
    aid = affiliations.create_affiliation(conn, wid, ACTOR, person_id=p, organisation_id=club,
                                          role="groundskeeper")
    assert affiliations.get_affiliation(conn, aid)["role"] == "groundskeeper"


# ---------------------------------------------- Rhymney / Moyston reference case


def test_rhymney_moyston_distinct_orgs_attribution_preserved(conn):
    wid = _ws(conn, "AFF RM WS")
    p = _person(conn, wid, "Long-serving Player")
    rhymney = _org(conn, wid, "Rhymney Cricket Club")
    moyston = _org(conn, wid, "Moyston Cricket Club")
    combined = _org(conn, wid, "Rhymney/Moyston Cricket Club")
    affiliations.create_affiliation(conn, wid, ACTOR, person_id=p, organisation_id=rhymney, role="player",
                                    valid_from=date(1975, 10, 1), valid_to=date(1979, 3, 31))
    affiliations.create_affiliation(conn, wid, ACTOR, person_id=p, organisation_id=moyston, role="player",
                                    valid_from=date(1979, 10, 1), valid_to=date(1980, 3, 31))
    affiliations.create_affiliation(conn, wid, ACTOR, person_id=p, organisation_id=combined, role="player",
                                    valid_from=date(1980, 10, 1), valid_to=date(1990, 3, 31))
    career = affiliations.person_career(conn, p)
    orgs = {a["organisation_id"] for a in career}
    # Three distinct organisations retained — attribution per period preserved; no auto-combination.
    assert orgs == {rhymney, moyston, combined}
    assert len(career) == 3


# ---------------------------------------------- unknown / approximate periods


def test_unknown_and_approximate_periods(conn):
    wid = _ws(conn, "AFF WS3")
    p = _person(conn, wid, "Historical Player")
    club = _org(conn, wid, "Old Club")
    # No dates at all (unknown), preserved as such — never invented.
    a1 = affiliations.create_affiliation(conn, wid, ACTOR, person_id=p, organisation_id=club, role="player")
    assert affiliations.get_affiliation(conn, a1)["valid_from"] is None
    # Approximate period flagged.
    a2 = affiliations.create_affiliation(conn, wid, ACTOR, person_id=p, organisation_id=club, role="coach",
                                         valid_from=date(1950, 1, 1), date_approx=True,
                                         evidence="club centenary booklet, p.12")
    row = affiliations.get_affiliation(conn, a2)
    assert row["date_approx"] is True and row["evidence"] == "club centenary booklet, p.12"


# ---------------------------------------------- affiliation != participation


def test_affiliation_does_not_imply_match_participation(conn):
    """Club membership never establishes a match appearance — those come from match records only."""
    wid = _ws(conn, "AFF WS4")
    p = _person(conn, wid, "Member Only")
    club = _org(conn, wid, "Club")
    affiliations.create_affiliation(conn, wid, ACTOR, person_id=p, organisation_id=club, role="player",
                                    valid_from=date(2021, 10, 1))
    # The affiliation is recorded, but creating it writes no match-participation rows.
    assert len(affiliations.list_affiliations(conn, person_id=p)) == 1
    # No team-grade-season entries (the nearest participation record) are created by affiliation;
    # match appearances come only from match records (Phase 8).
    assert conn.execute(text("SELECT count(*) FROM team_grade_entry")).scalar_one() == 0


# ---------------------------------------------- verification / corrections


def test_verification_and_correction(conn):
    wid = _ws(conn, "AFF WS5")
    p = _person(conn, wid, "Researched Player")
    club = _org(conn, wid, "Club")
    aid = affiliations.create_affiliation(conn, wid, ACTOR, person_id=p, organisation_id=club, role="player")
    affiliations.set_verification(conn, wid, ACTOR, aid, status="verified")
    assert affiliations.get_affiliation(conn, aid)["verification_status"] == "verified"
    affiliations.correct_affiliation(conn, wid, ACTOR, aid, valid_from=date(1960, 1, 1), set_dates=True,
                                     role="captain", notes="corrected from minute book")
    row = affiliations.get_affiliation(conn, aid)
    assert row["valid_from"] == date(1960, 1, 1) and row["role"] == "captain"


# ---------------------------------------------- validation


def test_validation(conn):
    wid = _ws(conn, "AFF WS6")
    p = _person(conn, wid, "P")
    club = _org(conn, wid, "Club")
    other = _org(conn, wid, "Other Club")
    team_other = _team(conn, wid, other, "Other First XI")
    with pytest.raises(ValueError, match="person_not_found"):
        affiliations.create_affiliation(conn, wid, ACTOR, person_id=uuid.uuid4(), organisation_id=club)
    with pytest.raises(ValueError, match="organisation_not_found"):
        affiliations.create_affiliation(conn, wid, ACTOR, person_id=p, organisation_id=uuid.uuid4())
    # a team must belong to the affiliation's organisation
    with pytest.raises(ValueError, match="team_not_in_organisation"):
        affiliations.create_affiliation(conn, wid, ACTOR, person_id=p, organisation_id=club, team_id=team_other)
    with pytest.raises(ValueError, match="invalid_date_range"):
        affiliations.create_affiliation(conn, wid, ACTOR, person_id=p, organisation_id=club,
                                        valid_from=date(2000, 1, 1), valid_to=date(1999, 1, 1))


# ---------------------------------------------- isolation


def test_affiliations_isolated_across_workspaces(conn):
    wid_a = _mk_workspace(conn, "AFF ISO A")
    wid_b = _mk_workspace(conn, "AFF ISO B")
    set_workspace(conn, wid_a)
    p = _person(conn, wid_a, "A Person")
    org = _org(conn, wid_a, "A Club")
    aid = affiliations.create_affiliation(conn, wid_a, ACTOR, person_id=p, organisation_id=org, role="player")
    set_workspace(conn, wid_b)
    assert affiliations.get_affiliation(conn, aid) is None
    assert affiliations.list_affiliations(conn) == []


# ---------------------------------------------- permissions + audit


def test_permission_and_audit(conn):
    wid = _ws(conn, "AFF PERM WS")
    admin = _mk_user(conn, "aff_admin")
    viewer = _mk_user(conn, "aff_viewer")
    permissions.grant_role(conn, admin, wid, "workspace_admin")
    permissions.grant_role(conn, viewer, wid, "viewer")
    assert "person.manage" in permissions.effective_permissions(conn, admin, wid, False)
    assert "person.manage" not in permissions.effective_permissions(conn, viewer, wid, False)

    p = _person(conn, wid, "Audit Person")
    club = _org(conn, wid, "Club")
    aid = affiliations.create_affiliation(conn, wid, ACTOR, person_id=p, organisation_id=club, role="player")
    affiliations.set_verification(conn, wid, ACTOR, aid, status="verified")
    affiliations.correct_affiliation(conn, wid, ACTOR, aid, notes="n")
    actions = conn.execute(
        text("SELECT action FROM audit_log WHERE action LIKE 'person_affiliation%'")
    ).scalars().all()
    for expected in ("person_affiliation.create", "person_affiliation.verify", "person_affiliation.correct"):
        assert expected in actions
