"""Live venue & team tests (Phase 4, Stage 2).

Rolled back in a single transaction (no data persists); skipped without a live DB. Runs as the
least-privilege ``onestats_app`` role under FORCE RLS, so workspace isolation is exercised for
real. Covers creation, historical names + period-correct resolution, organisation/program
relationships, source-identity preservation, duplicate detection, reversible merge, distinct
assertions, workspace isolation (incl. cross-workspace merge), permissions, audit and invalid
inputs.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import organisations, permissions, teams, venues

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


def _mk_user(conn, username):
    return conn.execute(
        text("INSERT INTO app_user(username) VALUES (:u) RETURNING id"), {"u": username}
    ).scalar_one()


def _ws(conn, name):
    wid = _mk_workspace(conn, name)
    set_workspace(conn, wid)
    return wid


def _org(conn, wid, name, **kw):
    return organisations.create_organisation(conn, wid, ACTOR, name=name, **kw)


# ---------------------------------------------------------------- venues: basics


def test_venue_create_update_and_unknown_not_invented(conn):
    wid = _ws(conn, "VEN WS1")
    vid = venues.create_venue(
        conn, wid, ACTOR, name="Victoria Park", locality="Rhymney", postcode="?"
    )
    v = venues.get_venue(conn, vid)
    assert v["name"] == "Victoria Park"
    assert v["locality"] == "Rhymney"
    assert v["postcode"] is None  # "?" stored as unknown, never invented
    assert v["latitude"] is None and v["longitude"] is None
    updated = venues.update_venue(conn, wid, ACTOR, vid, region="Victoria", country="Australia")
    assert updated["region"] == "Victoria" and updated["country"] == "Australia"


def test_venue_is_standalone_and_reusable(conn):
    """A venue belongs to no organisation, so it can be reused by many clubs/teams."""
    wid = _ws(conn, "VEN WS2")
    vid = venues.create_venue(conn, wid, ACTOR, name="Central Oval")
    v = venues.get_venue(conn, vid)
    assert "organisation_id" not in v  # venues carry no owning organisation
    assert vid in {x["id"] for x in venues.list_venues(conn)}


def test_venue_historical_names_and_period_resolution(conn):
    wid = _ws(conn, "VEN WS3")
    vid = venues.create_venue(conn, wid, ACTOR, name="New Ground")
    venues.add_name_history(
        conn, wid, ACTOR, vid, name="Old Paddock", valid_from=date(1900, 1, 1), valid_to=date(1969, 12, 31)
    )
    venues.add_name_history(conn, wid, ACTOR, vid, name="New Ground", valid_from=date(1970, 1, 1))
    assert venues.name_as_of(conn, vid, date(1950, 1, 1)) == "Old Paddock"
    assert venues.name_as_of(conn, vid, date(2000, 1, 1)) == "New Ground"


def test_venue_source_identity_idempotent_and_merge_reversible(conn):
    wid = _ws(conn, "VEN WS4")
    keep = venues.create_venue(conn, wid, ACTOR, name="Keep Oval", source_system="cs", source_ref="V-1")
    dup = venues.create_venue(conn, wid, ACTOR, name="Dup Oval", source_system="cs", source_ref="V-2")
    # idempotent re-import
    again = venues.add_source_identity(conn, wid, ACTOR, keep, source_system="cs", source_ref="V-1")
    assert again["created"] is False
    assert len(venues.list_source_identities(conn, keep)) == 1

    res = venues.merge_venues(conn, wid, ACTOR, keep, dup, reason="same ground")
    assert venues.get_venue(conn, dup)["merged_into_id"] == keep
    assert len(venues.list_source_identities(conn, dup)) == 1  # merged record preserved
    assert dup not in {v["id"] for v in venues.list_venues(conn)}
    venues.undo_merge(conn, wid, ACTOR, res["merge_id"])
    assert venues.get_venue(conn, dup)["merged_into_id"] is None


def test_venue_distinct_assertion_blocks_merge(conn):
    wid = _ws(conn, "VEN WS5")
    a = venues.create_venue(conn, wid, ACTOR, name="Shared Name Oval")
    b = venues.create_venue(conn, wid, ACTOR, name="Shared Name Oval")
    assert any(c["venue_id"] == b for c in venues.find_duplicate_candidates(conn, a))
    venues.assert_distinct(conn, wid, ACTOR, a, b, reason="different towns")
    assert all(c["venue_id"] != b for c in venues.find_duplicate_candidates(conn, a))
    with pytest.raises(ValueError, match="asserted_distinct"):
        venues.merge_venues(conn, wid, ACTOR, a, b)


# ---------------------------------------------------------------- teams: basics


def test_team_create_links_org_and_program(conn):
    wid = _ws(conn, "TEAM WS1")
    org = _org(conn, wid, "Ararat CC")
    tid = teams.create_team(conn, wid, ACTOR, organisation_id=org, name="Ararat 1st XI", program="seniors")
    t = teams.get_team(conn, tid)
    assert t["organisation_id"] == org
    assert t["program"] == "seniors"
    womens = teams.create_team(conn, wid, ACTOR, organisation_id=org, name="Ararat Women", program="womens")
    assert teams.get_team(conn, womens)["program"] == "womens"
    assert {tid, womens} <= {t["id"] for t in teams.list_teams(conn, organisation_id=org)}
    assert [t["id"] for t in teams.list_teams(conn, organisation_id=org, program="womens")] == [womens]


def test_team_requires_existing_organisation(conn):
    import uuid
    wid = _ws(conn, "TEAM WS2")
    with pytest.raises(ValueError, match="organisation_not_found"):
        teams.create_team(conn, wid, ACTOR, organisation_id=uuid.uuid4(), name="Ghost XI")


def test_team_historical_names_and_resolution(conn):
    wid = _ws(conn, "TEAM WS3")
    org = _org(conn, wid, "Historic CC")
    tid = teams.create_team(conn, wid, ACTOR, organisation_id=org, name="Historic Seniors")
    teams.add_name_history(
        conn, wid, ACTOR, tid, name="Historic First XI", valid_from=date(1950, 1, 1), valid_to=date(1999, 12, 31)
    )
    assert teams.name_as_of(conn, tid, date(1980, 1, 1)) == "Historic First XI"


def test_team_duplicate_scoped_to_org_and_program(conn):
    wid = _ws(conn, "TEAM WS4")
    org1 = _org(conn, wid, "Club One")
    org2 = _org(conn, wid, "Club Two")
    a = teams.create_team(conn, wid, ACTOR, organisation_id=org1, name="First XI")
    b = teams.create_team(conn, wid, ACTOR, organisation_id=org1, name="First XI")  # same org+program
    other = teams.create_team(conn, wid, ACTOR, organisation_id=org2, name="First XI")  # different club
    cand_ids = {c["team_id"] for c in teams.find_duplicate_candidates(conn, a)}
    assert b in cand_ids
    assert other not in cand_ids  # two clubs' "First XI" are not duplicates


def test_team_merge_reversible_and_source_preserved(conn):
    wid = _ws(conn, "TEAM WS5")
    org = _org(conn, wid, "Merge CC")
    keep = teams.create_team(conn, wid, ACTOR, organisation_id=org, name="Keep XI")
    dup = teams.create_team(
        conn, wid, ACTOR, organisation_id=org, name="Dup XI", source_system="cs", source_ref="T-9"
    )
    res = teams.merge_teams(conn, wid, ACTOR, keep, dup, reason="same team")
    assert teams.get_team(conn, dup)["merged_into_id"] == keep
    assert len(teams.list_source_identities(conn, dup)) == 1
    teams.undo_merge(conn, wid, ACTOR, res["merge_id"])
    assert teams.get_team(conn, dup)["merged_into_id"] is None


def test_team_distinct_assertion_blocks_merge(conn):
    wid = _ws(conn, "TEAM WS6")
    org = _org(conn, wid, "Distinct CC")
    a = teams.create_team(conn, wid, ACTOR, organisation_id=org, name="Reserves")
    b = teams.create_team(conn, wid, ACTOR, organisation_id=org, name="Reserves")
    teams.assert_distinct(conn, wid, ACTOR, a, b, reason="two genuinely separate sides")
    with pytest.raises(ValueError, match="asserted_distinct"):
        teams.merge_teams(conn, wid, ACTOR, a, b)


# ---------------------------------------------------------- historical accuracy


def test_rhymney_moyston_teams_are_distinct_and_not_reassigned(conn):
    """Rhymney, Moyston and Rhymney/Moyston field distinct teams; merging the *organisations*
    never silently reassigns a historical team to the later organisation."""
    wid = _ws(conn, "RM WS")
    rhymney = _org(conn, wid, "Rhymney Cricket Club", is_historical=True)
    moyston = _org(conn, wid, "Moyston Cricket Club", is_historical=True)
    combined = _org(conn, wid, "Rhymney/Moyston Cricket Club")

    t_rhymney = teams.create_team(conn, wid, ACTOR, organisation_id=rhymney, name="Rhymney Seniors",
                                  is_historical=True, source_system="cs", source_ref="RHY-1")
    t_moyston = teams.create_team(conn, wid, ACTOR, organisation_id=moyston, name="Moyston Seniors",
                                  is_historical=True, source_system="cs", source_ref="MOY-1")
    teams.create_team(conn, wid, ACTOR, organisation_id=combined, name="Rhymney/Moyston Seniors")

    # Three distinct teams attributable to three distinct organisations.
    assert len({t_rhymney, t_moyston}) == 2
    assert teams.get_team(conn, t_rhymney)["organisation_id"] == rhymney
    assert teams.get_team(conn, t_moyston)["organisation_id"] == moyston
    # Original source identifiers retained.
    assert teams.list_source_identities(conn, t_rhymney)[0]["source_ref"] == "RHY-1"

    # Even if the organisations are merged, the historical teams keep their original attribution.
    organisations.merge_organisations(conn, wid, ACTOR, combined, moyston, reason="club amalgamation")
    assert teams.get_team(conn, t_moyston)["organisation_id"] == moyston  # NOT reassigned to combined


# ------------------------------------------------------------- isolation


def test_cross_workspace_isolation_and_merge(conn):
    wid_a = _mk_workspace(conn, "VT ISO A")
    wid_b = _mk_workspace(conn, "VT ISO B")
    set_workspace(conn, wid_a)
    v_a = venues.create_venue(conn, wid_a, ACTOR, name="Oval A")
    org_a = _org(conn, wid_a, "Org A")
    t_a = teams.create_team(conn, wid_a, ACTOR, organisation_id=org_a, name="Team A")
    set_workspace(conn, wid_b)
    v_b = venues.create_venue(conn, wid_b, ACTOR, name="Oval B")
    org_b = _org(conn, wid_b, "Org B")
    t_b = teams.create_team(conn, wid_b, ACTOR, organisation_id=org_b, name="Team B")

    set_workspace(conn, wid_a)
    assert v_b not in {v["id"] for v in venues.list_venues(conn)}
    assert t_b not in {t["id"] for t in teams.list_teams(conn)}
    assert venues.get_venue(conn, v_b) is None
    assert teams.get_team(conn, t_b) is None
    # Cross-workspace merges cannot even be formed.
    with pytest.raises(ValueError, match="venue_not_found"):
        venues.merge_venues(conn, wid_a, ACTOR, v_a, v_b)
    with pytest.raises(ValueError, match="team_not_found"):
        teams.merge_teams(conn, wid_a, ACTOR, t_a, t_b)


# ------------------------------------------------------------- permissions


def test_permission_matrix_for_venue_and_team_management(conn):
    wid = _ws(conn, "VT PERM WS")
    admin = _mk_user(conn, "vt_admin")
    viewer = _mk_user(conn, "vt_viewer")
    permissions.grant_role(conn, admin, wid, "workspace_admin")
    permissions.grant_role(conn, viewer, wid, "viewer")
    admin_perms = permissions.effective_permissions(conn, admin, wid, False)
    viewer_perms = permissions.effective_permissions(conn, viewer, wid, False)
    assert {"venue.manage", "organisation.manage"} <= admin_perms
    assert "venue.manage" not in viewer_perms
    assert "organisation.manage" not in viewer_perms


# ------------------------------------------------------------- audit


def test_venue_and_team_changes_are_audited(conn):
    wid = _ws(conn, "VT AUDIT WS")
    org = _org(conn, wid, "Audit Org")
    v1 = venues.create_venue(conn, wid, ACTOR, name="Audit Oval 1")
    v2 = venues.create_venue(conn, wid, ACTOR, name="Audit Oval 2")
    vres = venues.merge_venues(conn, wid, ACTOR, v1, v2)
    venues.undo_merge(conn, wid, ACTOR, vres["merge_id"])
    t1 = teams.create_team(conn, wid, ACTOR, organisation_id=org, name="Audit XI 1")
    t2 = teams.create_team(conn, wid, ACTOR, organisation_id=org, name="Audit XI 2")
    teams.merge_teams(conn, wid, ACTOR, t1, t2)
    actions = conn.execute(
        text("SELECT action FROM audit_log WHERE action LIKE 'venue%' OR action LIKE 'team%'")
    ).scalars().all()
    for expected in ("venue.create", "venue.merge", "venue.merge.undo", "team.create", "team.merge"):
        assert expected in actions


# ------------------------------------------------------------- invalid inputs


def test_invalid_and_conflicting_inputs(conn):
    wid = _ws(conn, "VT INVALID WS")
    org = _org(conn, wid, "Invalid Org")
    with pytest.raises(ValueError, match="missing_name"):
        venues.create_venue(conn, wid, ACTOR, name="   ")
    with pytest.raises(ValueError, match="invalid_program"):
        teams.create_team(conn, wid, ACTOR, organisation_id=org, name="X", program="banana")
    v = venues.create_venue(conn, wid, ACTOR, name="Solo Oval")
    with pytest.raises(ValueError, match="cannot_merge_same"):
        venues.merge_venues(conn, wid, ACTOR, v, v)
    # conflicting merge: cannot merge an already-merged team
    a = teams.create_team(conn, wid, ACTOR, organisation_id=org, name="A")
    b = teams.create_team(conn, wid, ACTOR, organisation_id=org, name="B")
    c = teams.create_team(conn, wid, ACTOR, organisation_id=org, name="C")
    teams.merge_teams(conn, wid, ACTOR, a, b)
    with pytest.raises(ValueError, match="already_merged"):
        teams.merge_teams(conn, wid, ACTOR, c, b)
