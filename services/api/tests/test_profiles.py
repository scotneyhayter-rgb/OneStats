"""Live player-profile tests (Phase 5, Stage 4).

Rolled back in a single transaction (no data persists); skipped without a live DB. Runs as the
least-privilege ``onestats_app`` role under FORCE RLS. Covers profile upsert, player numbers,
leadership, recognition, photo metadata, the career view (incl. Rhymney/Moyston per-org
attribution + documented related organisations), the reserved statistics contract (no fabricated
figures), privacy/public separation, isolation, permissions and audit. Photo file storage is
covered by a separate filesystem unit test (``test_photos_storage.py``).
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import affiliations, people, permissions, profiles, relationships

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


# ----------------------------------------------------------- profile is 1:1 on person_id


def test_profile_upsert_is_one_to_one(conn):
    wid = _ws(conn, "PROF WS1")
    p = _person(conn, wid, "Scotney Hayter")
    profiles.upsert_profile(conn, wid, ACTOR, p, preferred_display_name="S Hayter",
                            batting_style="right_hand", bowling_style="right_arm_medium",
                            is_wicketkeeper=True, player_status="current", public_visible=True)
    prof = profiles.get_profile(conn, p)
    assert prof["preferred_display_name"] == "S Hayter" and prof["is_wicketkeeper"] is True
    # update, still one row
    profiles.upsert_profile(conn, wid, ACTOR, p, biography="All-rounder.")
    assert conn.execute(text("SELECT count(*) FROM person_profile WHERE person_id = :p"), {"p": p}).scalar_one() == 1
    assert profiles.get_profile(conn, p)["biography"] == "All-rounder."
    assert profiles.get_profile(conn, p)["preferred_display_name"] == "S Hayter"  # preserved


def test_no_fabricated_statistics(conn):
    wid = _ws(conn, "PROF WS1b")
    p = _person(conn, wid, "Player")
    contract = profiles.career_statistics_contract(p)
    assert contract["status"] == "not_available"
    assert all(v["value"] is None and v["status"] == "not_available" for v in contract["statistics"].values())
    assert "matches_played" in contract["statistics"] and "captaincy_win_pct" in contract["statistics"]


# ----------------------------------------------------------- numbers / leadership / recognition


def test_player_numbers_historical_and_reusable(conn):
    wid = _ws(conn, "PROF WS2")
    p1 = _person(conn, wid, "Player One")
    p2 = _person(conn, wid, "Player Two")
    club_a = _org(conn, wid, "Club A")
    club_b = _org(conn, wid, "Club B")
    # different numbers at different clubs / seasons; unknown number allowed
    profiles.add_number(conn, wid, ACTOR, p1, organisation_id=club_a, number="7", season_label="2020/21")
    profiles.add_number(conn, wid, ACTOR, p1, organisation_id=club_b, number="12", season_label="2021/22")
    profiles.add_number(conn, wid, ACTOR, p1, organisation_id=club_a, number=None, season_label="1999/00")
    # the same number used by a different player at a different time
    profiles.add_number(conn, wid, ACTOR, p2, organisation_id=club_a, number="7", season_label="2015/16")
    assert len(profiles.list_numbers(conn, p1)) == 3
    sevens = conn.execute(text("SELECT count(*) FROM person_number WHERE number = '7'")).scalar_one()
    assert sevens == 2  # same number, two different people — not an identifier


def test_leadership_distinct_from_match_captaincy(conn):
    wid = _ws(conn, "PROF WS3")
    p = _person(conn, wid, "Skipper")
    club = _org(conn, wid, "Club")
    profiles.add_leadership(conn, wid, ACTOR, p, organisation_id=club, role="captain", season_label="2022/23")
    profiles.add_leadership(conn, wid, ACTOR, p, organisation_id=club, role="coach", season_label="2023/24")
    roles = {lead["role"] for lead in profiles.list_leadership(conn, p)}
    assert {"captain", "coach"} <= roles
    # appointed leadership writes no match-captaincy stat (that comes from match records, Phase 8)
    contract = profiles.career_statistics_contract(p)
    assert contract["statistics"]["matches_captained"]["value"] is None


def test_recognition_tied_to_awarding_org(conn):
    wid = _ws(conn, "PROF WS4")
    p = _person(conn, wid, "Life Member")
    rhymney = _org(conn, wid, "Rhymney Cricket Club")
    profiles.add_recognition(conn, wid, ACTOR, p, recognition_type="life_member", organisation_id=rhymney,
                             title="Life Member", awarded_on=date(1995, 4, 1), evidence="AGM minutes 1995")
    rec = profiles.list_recognition(conn, p)[0]
    assert rec["recognition_type"] == "life_member" and rec["organisation_id"] == rhymney
    # a representative honour may have no club
    profiles.add_recognition(conn, wid, ACTOR, p, recognition_type="representative_honour",
                             title="Grampians XI", organisation_id=None)
    assert any(r["organisation_id"] is None for r in profiles.list_recognition(conn, p))


# ----------------------------------------------------------- photo metadata


def test_photo_metadata_primary_toggle(conn):
    wid = _ws(conn, "PROF WS5")
    p = _person(conn, wid, "Photogenic")
    profiles.register_photo(conn, wid, ACTOR, p, media_key="photo-a.jpg", is_primary=True, caption="1990")
    profiles.register_photo(conn, wid, ACTOR, p, media_key="photo-b.jpg", is_primary=True, caption="2000")
    photos = profiles.list_photos(conn, p)
    primaries = [ph for ph in photos if ph["is_primary"]]
    assert len(primaries) == 1 and primaries[0]["media_key"] == "photo-b.jpg"  # only one primary


# ----------------------------------------------------------- career view (RMCC) + privacy


def test_career_view_preserves_per_org_attribution_and_lists_related_orgs(conn):
    wid = _ws(conn, "PROF RM")
    p = _person(conn, wid, "RMCC Veteran")
    rhymney = _org(conn, wid, "Rhymney Cricket Club")
    _org(conn, wid, "Moyston Cricket Club")  # distinct historical org (not used in this view)
    combined = _org(conn, wid, "Rhymney/Moyston Cricket Club")
    affiliations.create_affiliation(conn, wid, ACTOR, person_id=p, organisation_id=rhymney, role="player",
                                    valid_from=date(1975, 10, 1), valid_to=date(1979, 3, 31))
    affiliations.create_affiliation(conn, wid, ACTOR, person_id=p, organisation_id=combined, role="player",
                                    valid_from=date(1980, 10, 1))
    # documented amalgamation relationship (Phase 4) — surfaced, never auto-merged
    relationships.create_relationship(conn, wid, ACTOR, from_org_id=rhymney, to_org_id=combined,
                                      rel_type="amalgamation", valid_from=date(1980, 1, 1))
    view = profiles.career_view(conn, p)
    org_ids = {a["organisation_id"] for a in view["affiliations"]}
    assert {rhymney, combined} <= org_ids  # per-org attribution preserved
    assert any(r["rel_type"] == "amalgamation" for r in view["related_organisations"])
    assert view["statistics"]["status"] == "not_available"


def test_career_view_played_for_clubs_from_matches_excludes_recorded_affiliations(conn):
    import json

    wid = _ws(conn, "PLAYED FOR")
    p = _person(conn, wid, "A Allrounder")
    affiliated_org = _org(conn, wid, "Rhymney Cricket Club")
    appearance_org = _org(conn, wid, "Moyston Cricket Club")   # linked only via a match appearance
    # A recorded affiliation to Rhymney only — Moyston has none.
    affiliations.create_affiliation(conn, wid, ACTOR, person_id=p, organisation_id=affiliated_org, role="player",
                                    valid_from=date(1980, 10, 1))
    aff_team = conn.execute(text("INSERT INTO team(workspace_id, organisation_id, name) VALUES (:w,:o,'Rhymney XI') "
                                 "RETURNING id"), {"w": wid, "o": affiliated_org}).scalar_one()
    app_team = conn.execute(text("INSERT INTO team(workspace_id, organisation_id, name) VALUES (:w,:o,'Moyston XI') "
                                 "RETURNING id"), {"w": wid, "o": appearance_org}).scalar_one()
    match1 = conn.execute(text("INSERT INTO match(workspace_id) VALUES (:w) RETURNING id"), {"w": wid}).scalar_one()
    match2 = conn.execute(text("INSERT INTO match(workspace_id) VALUES (:w) RETURNING id"), {"w": wid}).scalar_one()
    # The player appeared for a Rhymney team in one match and a Moyston team in another.
    conn.execute(
        text("INSERT INTO match_stat_contribution(workspace_id, match_id, calculator, subject_kind, subject_id, "
             "team_id, metrics) VALUES (:w,:m,'player_appearance','person',:sid,:tid, CAST(:met AS jsonb))"),
        [{"w": wid, "m": str(match1), "sid": str(p), "tid": str(aff_team), "met": json.dumps({"matches": 1})},
         {"w": wid, "m": str(match2), "sid": str(p), "tid": str(app_team), "met": json.dumps({"matches": 1})}],
    )
    view = profiles.career_view(conn, p, workspace_id=wid)
    clubs = {c["org_id"] for c in view["played_for_clubs"]}
    # Moyston (appearance only) is listed; Rhymney (a recorded affiliation) is NOT duplicated here.
    assert str(appearance_org) in clubs
    assert str(affiliated_org) not in clubs
    assert all("org_id" in c and "club" in c for c in view["played_for_clubs"])
    # Without a workspace_id the field is present but empty (no appearance lookup performed).
    assert profiles.career_view(conn, p)["played_for_clubs"] == []


def test_public_view_strips_internal_and_hidden(conn):
    wid = _ws(conn, "PROF PRIV")
    # public (non-junior) person with a public-visible profile
    p = _person(conn, wid, "Public Player")
    profiles.upsert_profile(conn, wid, ACTOR, p, biography="Bio.", research_notes="internal only",
                            public_visible=True)
    pub = profiles.career_view(conn, p, public=True)
    assert pub["profile"]["biography"] == "Bio."
    assert "research_notes" not in pub["profile"]  # internal field stripped

    # profile not marked public -> no profile in public view
    p2 = _person(conn, wid, "Private Player")
    profiles.upsert_profile(conn, wid, ACTOR, p2, biography="Hidden", public_visible=False)
    assert profiles.career_view(conn, p2, public=True)["profile"] is None

    # a junior is never exposed publicly
    junior = _person(conn, wid, "Junior", is_junior=True)
    profiles.upsert_profile(conn, wid, ACTOR, junior, public_visible=True)
    assert profiles.career_view(conn, junior, public=True) is None


# ----------------------------------------------------------- isolation / permissions / audit


def test_isolation(conn):
    wid_a = _mk_workspace(conn, "PROF ISO A")
    wid_b = _mk_workspace(conn, "PROF ISO B")
    set_workspace(conn, wid_a)
    p = _person(conn, wid_a, "A Person")
    profiles.upsert_profile(conn, wid_a, ACTOR, p, biography="A")
    set_workspace(conn, wid_b)
    assert profiles.get_profile(conn, p) is None
    assert profiles.career_view(conn, p) is None


def test_permission_and_audit(conn):
    wid = _ws(conn, "PROF PERM")
    admin = _mk_user(conn, "prof_admin")
    viewer = _mk_user(conn, "prof_viewer")
    permissions.grant_role(conn, admin, wid, "workspace_admin")
    permissions.grant_role(conn, viewer, wid, "viewer")
    assert "person.manage" in permissions.effective_permissions(conn, admin, wid, False)
    assert "person.manage" not in permissions.effective_permissions(conn, viewer, wid, False)

    p = _person(conn, wid, "Audit Player")
    club = _org(conn, wid, "Club")
    profiles.upsert_profile(conn, wid, ACTOR, p, biography="b")
    profiles.add_number(conn, wid, ACTOR, p, organisation_id=club, number="1")
    profiles.add_leadership(conn, wid, ACTOR, p, organisation_id=club, role="captain")
    profiles.add_recognition(conn, wid, ACTOR, p, recognition_type="life_member", organisation_id=club)
    profiles.register_photo(conn, wid, ACTOR, p, media_key="x.jpg")
    actions = conn.execute(
        text("SELECT action FROM audit_log WHERE action LIKE 'person_profile%' OR action LIKE 'person_number%' "
             "OR action LIKE 'person_leadership%' OR action LIKE 'person_recognition%' OR action LIKE 'person_photo%'")
    ).scalars().all()
    for expected in ("person_profile.create", "person_number.add", "person_leadership.add",
                     "person_recognition.add", "person_photo.register"):
        assert expected in actions


def test_validation(conn):
    import uuid
    wid = _ws(conn, "PROF INVALID")
    with pytest.raises(ValueError, match="person_not_found"):
        profiles.upsert_profile(conn, wid, ACTOR, uuid.uuid4(), biography="x")
    p = _person(conn, wid, "P")
    with pytest.raises(ValueError, match="invalid_player_status"):
        profiles.upsert_profile(conn, wid, ACTOR, p, player_status="legend")
    with pytest.raises(ValueError, match="organisation_not_found"):
        profiles.add_number(conn, wid, ACTOR, p, organisation_id=uuid.uuid4(), number="1")
