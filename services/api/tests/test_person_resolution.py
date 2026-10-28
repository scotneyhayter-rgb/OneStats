"""Live person identity-resolution tests (Phase 5, Stage 3).

Rolled back in a single transaction (no data persists); skipped without a live DB. Runs as the
least-privilege ``onestats_app`` role under FORCE RLS. Covers evidence-based detection, the
Walker (same) / Bonner (different) / J Smith (uncertain) scenarios, administrator-approved
reversible merges, circular-merge prevention, distinct assertions respected on re-detection,
the review queue, statistical-integrity preservation, isolation, permissions and audit.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import affiliations, people, permissions
from onestats.domain import person_resolution as pr

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


def _org(conn, wid, name):
    return conn.execute(
        text("INSERT INTO organisation(workspace_id, name, kind) VALUES (:w, :n, 'club') RETURNING id"),
        {"w": wid, "n": name},
    ).scalar_one()


def _person(conn, wid, name, **kw):
    return people.create_person(conn, wid, ACTOR, display_name=name, **kw)


# ---------------------------------------------- detection: name alone is never proof


def test_same_name_is_weak_shared_club_is_medium(conn):
    wid = _ws(conn, "RES WS1")
    club = _org(conn, wid, "Rhymney CC")
    a = _person(conn, wid, "D Walker")
    b = _person(conn, wid, "D Walker")
    # name-only match -> weak
    cands = pr.find_duplicate_candidates(conn, a)
    assert any(c["person_id"] == b and c["confidence"] == "weak" for c in cands)
    # add a shared club affiliation -> corroborating evidence raises confidence to medium
    affiliations.create_affiliation(conn, wid, ACTOR, person_id=a, organisation_id=club, role="player")
    affiliations.create_affiliation(conn, wid, ACTOR, person_id=b, organisation_id=club, role="player")
    cands = pr.find_duplicate_candidates(conn, a)
    match = next(c for c in cands if c["person_id"] == b)
    assert match["confidence"] == "medium"
    assert "shared_club_affiliation" in match["evidence"]


def test_alias_match_detected(conn):
    wid = _ws(conn, "RES WS1b")
    a = _person(conn, wid, "John Smith")
    b = _person(conn, wid, "J Smith")
    people.add_name(conn, wid, ACTOR, a, name="J Smith", name_type="initials")
    cands = pr.find_duplicate_candidates(conn, b)
    assert any(c["person_id"] == a for c in cands)  # matched via alias, still weak


def test_scan_lists_workspace_duplicate_pairs(conn):
    """The workspace-wide scan drives the identity review worklist: cross-club same-name players are
    weak pairs, same-club same-name are medium, and pairs that are merged or marked distinct drop out."""
    wid = _ws(conn, "RES SCAN")
    club_r, club_m = _org(conn, wid, "Rhymney CC"), _org(conn, wid, "Moyston CC")

    def _pairs():
        return {frozenset((str(p["person_a_id"]), str(p["person_b_id"]))): p
                for p in pr.scan_duplicate_pairs(conn, wid)}

    # same player across two clubs -> same name, DIFFERENT clubs -> weak
    a, b = _person(conn, wid, "A Bonner"), _person(conn, wid, "A Bonner")
    affiliations.create_affiliation(conn, wid, ACTOR, person_id=a, organisation_id=club_r, role="player")
    affiliations.create_affiliation(conn, wid, ACTOR, person_id=b, organisation_id=club_m, role="player")
    # same name AND same club -> medium
    c, d = _person(conn, wid, "B Webb"), _person(conn, wid, "B Webb")
    affiliations.create_affiliation(conn, wid, ACTOR, person_id=c, organisation_id=club_r, role="player")
    affiliations.create_affiliation(conn, wid, ACTOR, person_id=d, organisation_id=club_r, role="player")
    _person(conn, wid, "Z Unique")  # no pair

    pairs = _pairs()
    ab, cd = frozenset((str(a), str(b))), frozenset((str(c), str(d)))
    assert ab in pairs and pairs[ab]["confidence"] == "weak"
    assert {pairs[ab]["a_display_name"], pairs[ab]["b_display_name"]} == {"A Bonner"}
    assert cd in pairs and pairs[cd]["confidence"] == "medium" and "shared_club_affiliation" in pairs[cd]["evidence"]

    # mark the cross-club pair distinct -> it drops out of the worklist
    pr.assert_distinct(conn, wid, ACTOR, a, b)
    assert ab not in _pairs()
    # merge the same-club pair -> the merged record drops out too
    pr.merge_people(conn, wid, ACTOR, c, d)
    assert cd not in _pairs()


# ---------------------------------------------- Walker (same): admin-approved merge


def test_walker_merge_is_reversible_and_preserves_records(conn):
    wid = _ws(conn, "RES WALKER")
    a = _person(conn, wid, "D Walker", source_system="cs", source_ref="W-A")
    b = _person(conn, wid, "Darren Walker", source_system="cs", source_ref="W-B")
    club = _org(conn, wid, "Club")
    affiliations.create_affiliation(conn, wid, ACTOR, person_id=b, organisation_id=club, role="player")

    res = pr.merge_people(conn, wid, ACTOR, a, b, reason="same player (confirmed)", evidence="club records")
    merged = people.get_person(conn, b, include_protected=True)
    assert merged["merged_into_id"] == a and merged["status"] == "merged"
    assert pr.resolve_canonical(conn, b) == a
    # merged record keeps its own source ref + affiliation (nothing deleted/moved)
    assert len(people.list_source_identities(conn, b)) == 1
    assert len(affiliations.list_affiliations(conn, person_id=b)) == 1
    # default people listing excludes the merged record (no double counting)
    assert b not in {p["id"] for p in people.list_people(conn)}
    assert b in {p["id"] for p in people.list_people(conn, include_merged=True)}

    # reverse
    pr.undo_merge(conn, wid, ACTOR, res["merge_id"])
    reinstated = people.get_person(conn, b, include_protected=True)
    assert reinstated["merged_into_id"] is None and reinstated["status"] == "active"
    assert len(affiliations.list_affiliations(conn, person_id=b)) == 1  # affiliation intact


# ---------------------------------------------- Bonner (different): distinct assertion


def test_bonner_distinct_assertion_respected(conn):
    wid = _ws(conn, "RES BONNER")
    a = _person(conn, wid, "A Bonner", source_system="cs", source_ref="3555610")
    b = _person(conn, wid, "A Bonner", source_system="cs", source_ref="3569462")
    pr.assert_distinct(conn, wid, ACTOR, a, b, reason="two different people", evidence="different clubs/ages")
    assert pr.are_asserted_distinct(conn, a, b)
    # never re-suggested
    assert all(c["person_id"] != b for c in pr.find_duplicate_candidates(conn, a))
    # and can never be merged
    with pytest.raises(ValueError, match="asserted_distinct"):
        pr.merge_people(conn, wid, ACTOR, a, b)


# ---------------------------------------------- J Smith: uncertain, never auto-merged


def test_j_smith_uncertain_records_not_auto_merged(conn):
    wid = _ws(conn, "RES JSMITH")
    forms = ["J Smith", "Smith", "J. Smith", "John Smith"]
    ids = [_person(conn, wid, f) for f in forms]
    # Four distinct people remain; nothing is merged automatically.
    assert conn.execute(text("SELECT count(*) FROM person")).scalar_one() == 4
    # Competing possibilities can be recorded as reviews and deferred pending research.
    rid = pr.create_review(conn, wid, ACTOR, ids[0], ids[3], confidence="weak",
                           evidence="newspaper match report 1923", notes="possibly same")
    out = pr.decide_review(conn, wid, ACTOR, rid, decision="defer")
    assert out["status"] == "deferred"
    # still four distinct people
    assert conn.execute(text("SELECT count(*) FROM person WHERE merged_into_id IS NULL")).scalar_one() == 4


# ---------------------------------------------- merge guards


def test_merge_guards_prevent_conflicting_and_circular(conn):
    wid = _ws(conn, "RES GUARDS")
    a = _person(conn, wid, "A")
    b = _person(conn, wid, "B")
    c = _person(conn, wid, "C")
    with pytest.raises(ValueError, match="cannot_merge_same"):
        pr.merge_people(conn, wid, ACTOR, a, a)
    pr.merge_people(conn, wid, ACTOR, a, b)  # b -> a (a canonical)
    # b is already merged: it cannot be merged again into another record.
    with pytest.raises(ValueError, match="already_merged"):
        pr.merge_people(conn, wid, ACTOR, c, b)
    # Cannot merge *into* an already-merged record (this is what would otherwise create a chain/
    # cycle): b is merged, so it cannot be a canonical target.
    with pytest.raises(ValueError, match="canonical_already_merged"):
        pr.merge_people(conn, wid, ACTOR, b, c)
    # a stays the single surviving identity.
    assert pr.resolve_canonical(conn, b) == a


# ---------------------------------------------- review -> merge decision


def test_review_merge_decision(conn):
    wid = _ws(conn, "RES REVIEW")
    a = _person(conn, wid, "Same One")
    b = _person(conn, wid, "Same One")
    rid = pr.create_review(conn, wid, ACTOR, a, b, confidence="medium")
    out = pr.decide_review(conn, wid, ACTOR, rid, decision="merge", canonical_person_id=a,
                           reason="confirmed", evidence="scorecards")
    assert out["status"] == "merged"
    assert people.get_person(conn, b, include_protected=True)["merged_into_id"] == a
    # deciding an already-decided review is rejected
    with pytest.raises(ValueError, match="review_already_decided"):
        pr.decide_review(conn, wid, ACTOR, rid, decision="reject")


def test_review_distinct_decision_blocks_future_merge(conn):
    wid = _ws(conn, "RES REVIEW2")
    a = _person(conn, wid, "A Bonner")
    b = _person(conn, wid, "A Bonner")
    rid = pr.create_review(conn, wid, ACTOR, a, b)
    pr.decide_review(conn, wid, ACTOR, rid, decision="distinct", reason="different people")
    assert pr.are_asserted_distinct(conn, a, b)


# ---------------------------------------------- isolation / permissions / audit


def test_isolation(conn):
    wid_a = _mk_workspace(conn, "RES ISO A")
    wid_b = _mk_workspace(conn, "RES ISO B")
    set_workspace(conn, wid_a)
    a = _person(conn, wid_a, "P1")
    b = _person(conn, wid_a, "P2")
    pr.assert_distinct(conn, wid_a, ACTOR, a, b)
    set_workspace(conn, wid_b)
    assert pr.list_merges(conn) == []
    assert pr.list_reviews(conn) == []


def test_permission_and_audit(conn):
    wid = _ws(conn, "RES PERM")
    admin = _mk_user(conn, "res_admin")
    viewer = _mk_user(conn, "res_viewer")
    permissions.grant_role(conn, admin, wid, "workspace_admin")
    permissions.grant_role(conn, viewer, wid, "viewer")
    assert "person.manage" in permissions.effective_permissions(conn, admin, wid, False)
    assert "person.manage" not in permissions.effective_permissions(conn, viewer, wid, False)

    a = _person(conn, wid, "X")
    b = _person(conn, wid, "Y")
    res = pr.merge_people(conn, wid, ACTOR, a, b)
    pr.undo_merge(conn, wid, ACTOR, res["merge_id"])
    c = _person(conn, wid, "Z1")
    d = _person(conn, wid, "Z2")
    pr.assert_distinct(conn, wid, ACTOR, c, d)
    actions = conn.execute(
        text("SELECT action FROM audit_log WHERE action LIKE 'person.merge%' OR action = 'person.assert_distinct'")
    ).scalars().all()
    for expected in ("person.merge", "person.merge.undo", "person.assert_distinct"):
        assert expected in actions


def test_invalid_inputs(conn):
    wid = _ws(conn, "RES INVALID")
    a = _person(conn, wid, "A")
    with pytest.raises(ValueError, match="same_person"):
        pr.assert_distinct(conn, wid, ACTOR, a, a)
    with pytest.raises(ValueError, match="person_not_found"):
        pr.merge_people(conn, wid, ACTOR, a, uuid.uuid4())
    with pytest.raises(ValueError, match="merge_not_found"):
        pr.undo_merge(conn, wid, ACTOR, uuid.uuid4())
