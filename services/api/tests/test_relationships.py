"""Live organisation-relationship & timeline tests (Phase 4, Stage 5).

Rolled back in a single transaction (no data persists); skipped without a live DB. Runs as the
least-privilege ``onestats_app`` role under FORCE RLS. Covers time-bounded relationships,
historical amalgamation vs. duplicate-record merge, association transfers (sequential vs.
overlapping), period-correct affiliation/identity resolution, reversal/correction, cycle
rejection, cross-workspace isolation, permissions and audit.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import organisations, permissions, relationships

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


# --------------------------------------------- relationships + effective dates


def test_create_relationship_with_effective_dates(conn):
    wid = _ws(conn, "REL WS1")
    club = _org(conn, wid, "Club A")
    assoc = _org(conn, wid, "District Association", kind="association")
    rid = relationships.create_relationship(
        conn, wid, ACTOR, from_org_id=club, to_org_id=assoc, rel_type="affiliation",
        valid_from=date(1950, 1, 1), valid_to=date(1979, 12, 31), evidence="league handbook 1950",
    )
    rel = relationships.get_relationship(conn, rid)
    assert rel["rel_type"] == "affiliation"
    assert rel["valid_from"] == date(1950, 1, 1)
    assert rel["evidence"] == "league handbook 1950"


def test_unknown_dates_remain_unresolved(conn):
    wid = _ws(conn, "REL WS1b")
    a = _org(conn, wid, "Old Club")
    b = _org(conn, wid, "New Club")
    rid = relationships.create_relationship(conn, wid, ACTOR, from_org_id=a, to_org_id=b, rel_type="predecessor")
    rel = relationships.get_relationship(conn, rid)
    assert rel["valid_from"] is None and rel["valid_to"] is None  # explicitly unknown, not invented


# --------------------------------------------- amalgamation vs duplicate merge


def test_amalgamation_is_not_an_identity_merge(conn):
    """Rhymney + Moyston -> Rhymney/Moyston as documented amalgamation relationships; the
    predecessor clubs remain independently identifiable (NOT merged, NOT reassigned)."""
    wid = _ws(conn, "REL RM WS")
    rhymney = _org(conn, wid, "Rhymney Cricket Club", is_historical=True)
    moyston = _org(conn, wid, "Moyston Cricket Club", is_historical=True)
    combined = _org(conn, wid, "Rhymney/Moyston Cricket Club")

    relationships.create_relationship(conn, wid, ACTOR, from_org_id=rhymney, to_org_id=combined,
                                      rel_type="amalgamation", valid_from=date(1980, 1, 1))
    relationships.create_relationship(conn, wid, ACTOR, from_org_id=moyston, to_org_id=combined,
                                      rel_type="amalgamation", valid_from=date(1980, 1, 1))

    # All three remain distinct, un-merged organisations with their own identities.
    for oid in (rhymney, moyston, combined):
        org = organisations.get_organisation(conn, oid)
        assert org is not None
        assert org["merged_into_id"] is None  # relationship did NOT trigger a Stage 1 merge
        assert organisations.resolve_canonical(conn, oid) == oid
    # The combined club has two documented predecessors.
    into_combined = relationships.list_relationships(conn, combined, direction="to")
    assert len(into_combined) == 2 and all(r["rel_type"] == "amalgamation" for r in into_combined)


def test_name_change_relationship_preserves_period_correct_names(conn):
    wid = _ws(conn, "REL NAME WS")
    org = _org(conn, wid, "Current Name CC")
    organisations.add_name_history(conn, wid, ACTOR, org, name="Founding Name CC",
                                   valid_from=date(1900, 1, 1), valid_to=date(1949, 12, 31))
    assert organisations.name_as_of(conn, org, date(1925, 1, 1)) == "Founding Name CC"
    assert organisations.name_as_of(conn, org, date(2020, 1, 1)) == "Current Name CC"


# --------------------------------------------- association transfers


def test_sequential_association_transfers_allowed_overlap_rejected(conn):
    """A club retains records from successive associations across non-overlapping periods, but an
    overlapping exclusive transfer is rejected."""
    wid = _ws(conn, "REL XFER WS")
    club = _org(conn, wid, "Rhymney/Moyston CC")
    ararat = _org(conn, wid, "Ararat District CA", kind="association")
    grampians = _org(conn, wid, "Grampians CA", kind="association")
    horsham = _org(conn, wid, "Horsham CA", kind="association")

    relationships.create_relationship(conn, wid, ACTOR, from_org_id=club, to_org_id=ararat,
                                      rel_type="association_transfer", valid_from=date(1980, 1, 1), valid_to=date(1999, 12, 31))
    relationships.create_relationship(conn, wid, ACTOR, from_org_id=club, to_org_id=grampians,
                                      rel_type="association_transfer", valid_from=date(2000, 1, 1), valid_to=date(2014, 12, 31))
    relationships.create_relationship(conn, wid, ACTOR, from_org_id=club, to_org_id=horsham,
                                      rel_type="association_transfer", valid_from=date(2015, 1, 1))
    # An overlapping exclusive transfer must be rejected.
    with pytest.raises(ValueError, match="overlapping_affiliation"):
        relationships.create_relationship(conn, wid, ACTOR, from_org_id=club, to_org_id=ararat,
                                          rel_type="association_transfer", valid_from=date(1990, 1, 1), valid_to=date(1995, 12, 31))


def test_period_correct_affiliation_resolution(conn):
    wid = _ws(conn, "REL AFFRES WS")
    club = _org(conn, wid, "Travelling CC")
    ararat = _org(conn, wid, "Ararat DCA", kind="association")
    horsham = _org(conn, wid, "Horsham CA", kind="association")
    relationships.create_relationship(conn, wid, ACTOR, from_org_id=club, to_org_id=ararat,
                                      rel_type="association_transfer", valid_from=date(1980, 1, 1), valid_to=date(1999, 12, 31))
    relationships.create_relationship(conn, wid, ACTOR, from_org_id=club, to_org_id=horsham,
                                      rel_type="association_transfer", valid_from=date(2000, 1, 1))
    assert relationships.resolve_affiliation(conn, club, date(1990, 6, 1))["to_org_id"] == ararat
    assert relationships.resolve_affiliation(conn, club, date(2010, 6, 1))["to_org_id"] == horsham
    # A date before any documented affiliation resolves to unknown (not guessed).
    assert relationships.resolve_affiliation(conn, club, date(1970, 1, 1)) is None


# --------------------------------------------- reversal & correction


def test_relationship_void_and_restore(conn):
    wid = _ws(conn, "REL VOID WS")
    a = _org(conn, wid, "A")
    b = _org(conn, wid, "B", kind="association")
    rid = relationships.create_relationship(conn, wid, ACTOR, from_org_id=a, to_org_id=b, rel_type="affiliation")
    relationships.void_relationship(conn, wid, ACTOR, rid)
    assert relationships.get_relationship(conn, rid)["is_void"] is True
    assert relationships.list_relationships(conn, a) == []  # void excluded by default
    assert len(relationships.list_relationships(conn, a, include_void=True)) == 1
    relationships.restore_relationship(conn, wid, ACTOR, rid)
    assert relationships.get_relationship(conn, rid)["is_void"] is False
    with pytest.raises(ValueError, match="not_void"):
        relationships.restore_relationship(conn, wid, ACTOR, rid)


def test_relationship_correction(conn):
    wid = _ws(conn, "REL CORRECT WS")
    a = _org(conn, wid, "A")
    b = _org(conn, wid, "B", kind="association")
    rid = relationships.create_relationship(conn, wid, ACTOR, from_org_id=a, to_org_id=b, rel_type="affiliation")
    relationships.correct_relationship(conn, wid, ACTOR, rid, valid_from=date(1960, 1, 1), set_dates=True,
                                       evidence="minutes book")
    rel = relationships.get_relationship(conn, rid)
    assert rel["valid_from"] == date(1960, 1, 1) and rel["evidence"] == "minutes book"


# --------------------------------------------- cycle / invalid guards


def test_cycle_and_self_relationship_rejected(conn):
    wid = _ws(conn, "REL CYCLE WS")
    a = _org(conn, wid, "A")
    b = _org(conn, wid, "B")
    c = _org(conn, wid, "C")
    with pytest.raises(ValueError, match="self_relationship"):
        relationships.create_relationship(conn, wid, ACTOR, from_org_id=a, to_org_id=a, rel_type="predecessor")
    relationships.create_relationship(conn, wid, ACTOR, from_org_id=a, to_org_id=b, rel_type="predecessor")
    relationships.create_relationship(conn, wid, ACTOR, from_org_id=b, to_org_id=c, rel_type="predecessor")
    # c -> a would close the loop a -> b -> c -> a.
    with pytest.raises(ValueError, match="relationship_cycle"):
        relationships.create_relationship(conn, wid, ACTOR, from_org_id=c, to_org_id=a, rel_type="predecessor")


def test_invalid_type_and_missing_org(conn):
    wid = _ws(conn, "REL INVALID WS")
    a = _org(conn, wid, "A")
    with pytest.raises(ValueError, match="invalid_rel_type"):
        relationships.create_relationship(conn, wid, ACTOR, from_org_id=a, to_org_id=uuid.uuid4(), rel_type="banana")
    with pytest.raises(ValueError, match="organisation_not_found"):
        relationships.create_relationship(conn, wid, ACTOR, from_org_id=a, to_org_id=uuid.uuid4(), rel_type="predecessor")


# --------------------------------------------- timeline


def test_timeline_assembles_names_and_relationships_with_uncertainty(conn):
    wid = _ws(conn, "REL TIMELINE WS")
    club = _org(conn, wid, "Rhymney/Moyston CC")
    rhymney = _org(conn, wid, "Rhymney CC", is_historical=True)
    organisations.add_name_history(conn, wid, ACTOR, club, name="Early Name",
                                   valid_from=date(1980, 1, 1), valid_to=date(1999, 12, 31))
    relationships.create_relationship(conn, wid, ACTOR, from_org_id=rhymney, to_org_id=club,
                                      rel_type="amalgamation")  # unknown date
    tl = relationships.organisation_timeline(conn, club)
    kinds = {e["kind"] for e in tl["events"]}
    assert {"name", "relationship"} <= kinds
    assert any(e["kind"] == "relationship" and e["uncertain"] for e in tl["events"])  # unknown date flagged
    assert tl["organisation"]["name"] == "Rhymney/Moyston CC"


# --------------------------------------------- isolation


def test_relationships_isolated_across_workspaces(conn):
    wid_a = _mk_workspace(conn, "REL ISO A")
    wid_b = _mk_workspace(conn, "REL ISO B")
    set_workspace(conn, wid_a)
    a1 = _org(conn, wid_a, "A1")
    a2 = _org(conn, wid_a, "A2", kind="association")
    rid = relationships.create_relationship(conn, wid_a, ACTOR, from_org_id=a1, to_org_id=a2, rel_type="affiliation")
    set_workspace(conn, wid_b)
    assert relationships.get_relationship(conn, rid) is None  # invisible in another workspace
    assert relationships.list_relationships(conn, a1) == []


# --------------------------------------------- permissions & audit


def test_permission_and_audit(conn):
    wid = _ws(conn, "REL PERM WS")
    admin = _mk_user(conn, "rel_admin")
    viewer = _mk_user(conn, "rel_viewer")
    permissions.grant_role(conn, admin, wid, "workspace_admin")
    permissions.grant_role(conn, viewer, wid, "viewer")
    assert "organisation.manage" in permissions.effective_permissions(conn, admin, wid, False)
    assert "organisation.manage" not in permissions.effective_permissions(conn, viewer, wid, False)

    a = _org(conn, wid, "A")
    b = _org(conn, wid, "B", kind="association")
    rid = relationships.create_relationship(conn, wid, ACTOR, from_org_id=a, to_org_id=b, rel_type="affiliation")
    relationships.void_relationship(conn, wid, ACTOR, rid)
    actions = conn.execute(
        text("SELECT action FROM audit_log WHERE action LIKE 'organisation_relationship%'")
    ).scalars().all()
    assert "organisation_relationship.create" in actions
    assert "organisation_relationship.void" in actions
