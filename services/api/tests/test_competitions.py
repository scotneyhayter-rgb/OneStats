"""Live competition-structure tests (Phase 4, Stage 3).

Rolled back in a single transaction (no data persists); skipped without a live DB. Runs as the
least-privilege ``onestats_app`` role under FORCE RLS. Covers competitions (with/without
association ownership), divisions, grades (+ historical names), seasons (two-calendar-year
labels, unknown dates), team-grade-season entries (incl. several teams from one club, a team in
several competitions, duplicate prevention), the finals/classification structure with unresolved
source values, workspace isolation, permissions, audit and invalid inputs.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import competitions, permissions, teams

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


def _mk_org(conn, name):
    return conn.execute(
        text("INSERT INTO organisation(workspace_id, name, kind) "
             "VALUES (current_setting('onestats.workspace_id',true)::uuid, :n, 'association') RETURNING id"),
        {"n": name},
    ).scalar_one()


def _mk_club(conn, name):
    return conn.execute(
        text("INSERT INTO organisation(workspace_id, name, kind) "
             "VALUES (current_setting('onestats.workspace_id',true)::uuid, :n, 'club') RETURNING id"),
        {"n": name},
    ).scalar_one()


def _mk_team(conn, wid, org, name):
    return teams.create_team(conn, wid, ACTOR, organisation_id=org, name=name)


def _ws(conn, name):
    wid = _mk_workspace(conn, name)
    set_workspace(conn, wid)
    return wid


# ------------------------------------------------------- competitions + association


def test_competition_with_and_without_association(conn):
    wid = _ws(conn, "COMP WS1")
    assoc = _mk_org(conn, "Grampians CA")
    owned = competitions.create_competition(conn, wid, ACTOR, name="Grampians League", association_id=assoc)
    indep = competitions.create_competition(conn, wid, ACTOR, name="Friendly Cup")  # independent
    assert competitions.get_competition(conn, owned)["association_id"] == assoc
    assert competitions.get_competition(conn, indep)["association_id"] is None
    assert {owned, indep} <= {c["id"] for c in competitions.list_competitions(conn)}
    assert [c["id"] for c in competitions.list_competitions(conn, association_id=assoc)] == [owned]


def test_competition_rename_preserves_history(conn):
    wid = _ws(conn, "COMP WS2")
    cid = competitions.create_competition(conn, wid, ACTOR, name="Old League Name")
    competitions.update_competition(conn, wid, ACTOR, cid, name="New League Name", name_change_note="reorganised")
    names = {h["name"] for h in competitions.list_name_history(conn, cid)}
    assert {"Old League Name", "New League Name"} <= names  # original NOT overwritten


def test_competition_association_not_found(conn):
    wid = _ws(conn, "COMP WS3")
    with pytest.raises(ValueError, match="association_not_found"):
        competitions.create_competition(conn, wid, ACTOR, name="X", association_id=uuid.uuid4())


def test_competition_can_become_independent(conn):
    wid = _ws(conn, "COMP WS3b")
    assoc = _mk_org(conn, "Dropme CA")
    cid = competitions.create_competition(conn, wid, ACTOR, name="Transferable Comp", association_id=assoc)
    competitions.update_competition(conn, wid, ACTOR, cid, clear_association=True)
    assert competitions.get_competition(conn, cid)["association_id"] is None


# ------------------------------------------------------- divisions / grades / seasons


def test_division_grade_and_historical_grade_names(conn):
    wid = _ws(conn, "COMP WS4")
    cid = competitions.create_competition(conn, wid, ACTOR, name="Structured League")
    div = competitions.create_division(conn, wid, ACTOR, cid, name="Senior Division")
    grade = competitions.create_grade(conn, wid, ACTOR, cid, name="A Grade", program="senior_mens", division_id=div)
    assert competitions.list_divisions(conn, cid)[0]["id"] == div
    assert competitions.list_grades(conn, cid)[0]["program"] == "senior_mens"
    # Historical grade name change is preserved.
    competitions.add_grade_name_history(conn, wid, ACTOR, grade, name="First Grade",
                                        valid_from=date(1950, 1, 1), valid_to=date(1989, 12, 31))
    assert competitions.grade_name_as_of(conn, grade, date(1970, 1, 1)) == "First Grade"
    competitions.rename_grade(conn, wid, ACTOR, grade, name="Premier A")
    names = {h["name"] for h in conn.execute(
        text("SELECT name FROM grade_name_history WHERE grade_id = :g"), {"g": grade}).mappings().all()}
    assert {"A Grade", "First Grade", "Premier A"} <= names


def test_grade_program_is_free_text_for_admin_defined_programs(conn):
    """No fixed enum / no hard-coded team-size limit: admins may define programs like mixed junior."""
    wid = _ws(conn, "COMP WS4b")
    cid = competitions.create_competition(conn, wid, ACTOR, name="Junior League")
    competitions.create_grade(conn, wid, ACTOR, cid, name="Under 14 Mixed", program="mixed_junior")
    assert competitions.list_grades(conn, cid)[0]["program"] == "mixed_junior"
    # grade table carries no max-players column — team-size restrictions live in Stage 4.
    cols = {r[0] for r in conn.execute(text(
        "SELECT column_name FROM information_schema.columns WHERE table_name='grade'"))}
    assert "max_players" not in cols


def test_seasons_span_two_years_and_allow_unknown_dates(conn):
    wid = _ws(conn, "COMP WS5")
    cid = competitions.create_competition(conn, wid, ACTOR, name="Seasonal League")
    s1 = competitions.create_season(conn, wid, ACTOR, cid, label="2026/27",
                                    start_date=date(2026, 10, 1), end_date=date(2027, 3, 31))
    s2 = competitions.create_season(conn, wid, ACTOR, cid, label="1919/20")  # unknown exact dates
    seasons = {s["label"]: s for s in competitions.list_seasons(conn, cid)}
    assert seasons["2026/27"]["start_date"] == date(2026, 10, 1)
    assert seasons["1919/20"]["start_date"] is None  # unknown stays unknown, not invented
    assert {s1, s2} == {s["id"] for s in competitions.list_seasons(conn, cid)}
    with pytest.raises(ValueError, match="duplicate_season"):
        competitions.create_season(conn, wid, ACTOR, cid, label="2026/27")


# ------------------------------------------------------- team-grade-season entries


def test_team_grade_entries_cover_historical_scenarios(conn):
    wid = _ws(conn, "COMP WS6")
    club = _mk_club(conn, "Ararat CC")
    cid = competitions.create_competition(conn, wid, ACTOR, name="District League")
    a_grade = competitions.create_grade(conn, wid, ACTOR, cid, name="A Grade")
    b_grade = competitions.create_grade(conn, wid, ACTOR, cid, name="B Grade")
    s24 = competitions.create_season(conn, wid, ACTOR, cid, label="2024/25")
    s25 = competitions.create_season(conn, wid, ACTOR, cid, label="2025/26")

    first_xi = _mk_team(conn, wid, club, "Ararat 1st XI")
    second_xi = _mk_team(conn, wid, club, "Ararat 2nd XI")

    # Same team in different grades across seasons.
    competitions.enter_team(conn, wid, ACTOR, team_id=first_xi, grade_id=b_grade, season_id=s24)
    competitions.enter_team(conn, wid, ACTOR, team_id=first_xi, grade_id=a_grade, season_id=s25)
    # Multiple teams from one club in the same competition/season.
    competitions.enter_team(conn, wid, ACTOR, team_id=second_xi, grade_id=b_grade, season_id=s25)
    assert len(competitions.list_entries(conn, team_id=first_xi)) == 2
    assert len(competitions.list_entries(conn, season_id=s25)) == 2

    # Duplicate prevention: the same (team, grade, season) is idempotent.
    dup = competitions.enter_team(conn, wid, ACTOR, team_id=first_xi, grade_id=b_grade, season_id=s24)
    assert dup["created"] is False


def test_team_can_participate_in_multiple_competitions(conn):
    wid = _ws(conn, "COMP WS7")
    club = _mk_club(conn, "Dual CC")
    team = _mk_team(conn, wid, club, "Dual 1st XI")
    comp1 = competitions.create_competition(conn, wid, ACTOR, name="Saturday League")
    comp2 = competitions.create_competition(conn, wid, ACTOR, name="Midweek Cup")
    g1 = competitions.create_grade(conn, wid, ACTOR, comp1, name="A")
    g2 = competitions.create_grade(conn, wid, ACTOR, comp2, name="Open")
    s1 = competitions.create_season(conn, wid, ACTOR, comp1, label="2025/26")
    s2 = competitions.create_season(conn, wid, ACTOR, comp2, label="2025/26")
    competitions.enter_team(conn, wid, ACTOR, team_id=team, grade_id=g1, season_id=s1)
    competitions.enter_team(conn, wid, ACTOR, team_id=team, grade_id=g2, season_id=s2)
    assert len(competitions.list_entries(conn, team_id=team)) == 2


def test_entry_rejects_grade_season_from_different_competitions(conn):
    wid = _ws(conn, "COMP WS8")
    club = _mk_club(conn, "Mismatch CC")
    team = _mk_team(conn, wid, club, "Mismatch XI")
    comp1 = competitions.create_competition(conn, wid, ACTOR, name="Comp One")
    comp2 = competitions.create_competition(conn, wid, ACTOR, name="Comp Two")
    g1 = competitions.create_grade(conn, wid, ACTOR, comp1, name="A")
    s2 = competitions.create_season(conn, wid, ACTOR, comp2, label="2025/26")
    with pytest.raises(ValueError, match="grade_season_competition_mismatch"):
        competitions.enter_team(conn, wid, ACTOR, team_id=team, grade_id=g1, season_id=s2)


# ------------------------------------------------------- finals / classifications


def test_classification_defaults_and_unresolved_preserved(conn):
    wid = _ws(conn, "COMP WS9")
    defaults = competitions.ensure_default_classifications(conn, wid, ACTOR)
    keys = {c["key"] for c in defaults if c["status"] == "confirmed"}
    assert {"home_away", "final", "semi_final", "preliminary_final", "grand_final"} <= keys
    gf = next(c for c in defaults if c["key"] == "grand_final")
    assert gf["is_final"] is True
    assert "other" in keys  # 'other' (is_final unknown) is part of the default vocabulary
    # idempotent: re-seeding adds nothing.
    competitions.ensure_default_classifications(conn, wid, ACTOR)
    assert len(competitions.list_classifications(conn, status="confirmed")) == len(keys)

    # An undocumented source value is preserved as unresolved (never guessed): is_final unknown.
    competitions.record_unresolved_classification(
        conn, wid, ACTOR, source_value="CS_ROUND_CODE_7", source_system="cricket_statz"
    )
    unresolved = competitions.list_classifications(conn, status="unresolved")
    assert len(unresolved) == 1
    assert unresolved[0]["is_final"] is None
    assert unresolved[0]["unresolved_source_value"] == "CS_ROUND_CODE_7"


# ------------------------------------------------------- isolation


def test_competition_isolation_across_workspaces(conn):
    wid_a = _mk_workspace(conn, "COMP ISO A")
    wid_b = _mk_workspace(conn, "COMP ISO B")
    set_workspace(conn, wid_a)
    comp_a = competitions.create_competition(conn, wid_a, ACTOR, name="A League")
    set_workspace(conn, wid_b)
    assert comp_a not in {c["id"] for c in competitions.list_competitions(conn)}
    assert competitions.get_competition(conn, comp_a) is None


# ------------------------------------------------------- permissions


def test_competition_manage_permission_matrix(conn):
    wid = _ws(conn, "COMP PERM WS")
    admin = _mk_user(conn, "comp_admin")
    viewer = _mk_user(conn, "comp_viewer")
    permissions.grant_role(conn, admin, wid, "workspace_admin")
    permissions.grant_role(conn, viewer, wid, "viewer")
    assert "competition.manage" in permissions.effective_permissions(conn, admin, wid, False)
    assert "competition.manage" not in permissions.effective_permissions(conn, viewer, wid, False)


# ------------------------------------------------------- audit


def test_competition_changes_are_audited(conn):
    wid = _ws(conn, "COMP AUDIT WS")
    club = _mk_club(conn, "Audit CC")
    team = _mk_team(conn, wid, club, "Audit XI")
    cid = competitions.create_competition(conn, wid, ACTOR, name="Audit League")
    g = competitions.create_grade(conn, wid, ACTOR, cid, name="A")
    s = competitions.create_season(conn, wid, ACTOR, cid, label="2025/26")
    competitions.enter_team(conn, wid, ACTOR, team_id=team, grade_id=g, season_id=s)
    actions = conn.execute(
        text("SELECT action FROM audit_log WHERE action LIKE 'competition%' "
             "OR action LIKE 'grade%' OR action LIKE 'season%' OR action LIKE 'team_grade_entry%'")
    ).scalars().all()
    for expected in ("competition.create", "grade.create", "season.create", "team_grade_entry.create"):
        assert expected in actions


# ------------------------------------------------------- invalid inputs


def test_invalid_inputs(conn):
    wid = _ws(conn, "COMP INVALID WS")
    with pytest.raises(ValueError, match="missing_name"):
        competitions.create_competition(conn, wid, ACTOR, name="  ")
    cid = competitions.create_competition(conn, wid, ACTOR, name="Valid Comp")
    with pytest.raises(ValueError, match="missing_label"):
        competitions.create_season(conn, wid, ACTOR, cid, label="")
    with pytest.raises(ValueError, match="team_not_found"):
        competitions.enter_team(conn, wid, ACTOR, team_id=uuid.uuid4(), grade_id=uuid.uuid4(), season_id=uuid.uuid4())


def test_delete_competition_removes_empty_competition_and_children(conn):
    """An empty competition (no matches) deletes, taking its grades with it. Audited."""
    wid = _ws(conn, "COMP DEL1")
    cid = competitions.create_competition(conn, wid, ACTOR, name="To Delete")
    competitions.create_grade(conn, wid, ACTOR, cid, name="A Grade", program="senior_mens")
    competitions.delete_competition(conn, wid, ACTOR, cid)
    assert competitions.get_competition(conn, cid) is None
    assert competitions.list_grades(conn, cid) == []


def test_delete_competition_not_found_raises(conn):
    wid = _ws(conn, "COMP DEL2")
    with pytest.raises(ValueError, match="competition_not_found"):
        competitions.delete_competition(conn, wid, ACTOR, uuid.uuid4())


def test_delete_competition_refuses_when_it_has_matches(conn):
    """A competition referenced by a match is protected: delete raises competition_has_matches."""
    wid = _ws(conn, "COMP DEL3")
    cid = competitions.create_competition(conn, wid, ACTOR, name="Has Matches")
    conn.execute(
        text("INSERT INTO match(workspace_id, competition_id, status) "
             "VALUES (current_setting('onestats.workspace_id',true)::uuid, :c, 'draft')"),
        {"c": cid},
    )
    with pytest.raises(ValueError, match="competition_has_matches"):
        competitions.delete_competition(conn, wid, ACTOR, cid)
