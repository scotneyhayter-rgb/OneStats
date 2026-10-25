"""Phase 13 (player profiles) — career/season/match aggregation composed from the one engine.

Multi-season career, merge-aware, unknown-aware. Rolled back; skipped without a live DB.
"""
from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import batting, bowling, competitions, matches, people, person_resolution
from onestats.domain import innings as inn
from onestats.domain.records import honours, player_profile

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


def _ws(conn, name):
    wid = conn.execute(text("INSERT INTO workspace(name, type) VALUES (:n,'club') RETURNING id"), {"n": name}).scalar_one()
    conn.execute(text("INSERT INTO app_user(id, username) VALUES (:a, :u) ON CONFLICT (id) DO NOTHING"),
                 {"a": ACTOR, "u": f"actor-{name}"})
    set_workspace(conn, wid)
    return wid


def _team(conn, wid, name):
    org = conn.execute(text("INSERT INTO organisation(workspace_id,name,kind) VALUES (:w,:n,'club') RETURNING id"),
                       {"w": wid, "n": name + " CC"}).scalar_one()
    return conn.execute(text("INSERT INTO team(workspace_id,organisation_id,name) VALUES (:w,:o,:n) RETURNING id"),
                        {"w": wid, "o": org, "n": name}).scalar_one()


def _season(conn, wid, comp, label, y):
    return conn.execute(text("INSERT INTO season(workspace_id,competition_id,label,start_date) VALUES (:w,:c,:l,:d) RETURNING id"),
                        {"w": wid, "c": comp, "l": label, "d": dt.date(y, 10, 1)}).scalar_one()


def _match(conn, wid, comp, season, home, away, p, *, runs, wkts=0):
    mid = matches.create_match(conn, wid, ACTOR, competition_id=comp, season_id=season)
    matches.set_team(conn, wid, ACTOR, mid, team_id=home, is_home=True)
    matches.set_team(conn, wid, ACTOR, mid, team_id=away, is_home=False)
    i1 = inn.create_innings(conn, wid, ACTOR, match_id=mid, inns_number=1, batting_team_id=home, bowling_team_id=away)
    batting.create_entry(conn, wid, ACTOR, innings_id=i1, person_id=p, batting_position=1,
                         runs=runs, balls_faced=(None if runs is None else 60), dismissal_type="bowled")
    if wkts:
        i2 = inn.create_innings(conn, wid, ACTOR, match_id=mid, inns_number=2, batting_team_id=away, bowling_team_id=home)
        bowling.create_entry(conn, wid, ACTOR, innings_id=i2, person_id=p, legal_balls=30, runs_conceded=20, wickets=wkts)
    matches.set_approval(conn, wid, ACTOR, mid, status="approved")
    return mid


def test_career_and_season_breakdown(conn):
    wid = _ws(conn, "PP CAREER")
    comp = competitions.create_competition(conn, wid, ACTOR, name="League")
    s1 = _season(conn, wid, comp, "2023/24", 2023)
    s2 = _season(conn, wid, comp, "2024/25", 2024)
    home, away = _team(conn, wid, "Home"), _team(conn, wid, "Away")
    p = people.create_person(conn, wid, ACTOR, display_name="All Rounder")
    conn.execute(text("UPDATE match SET season_id = :s WHERE id = :m"),
                 {"s": s1, "m": _match(conn, wid, comp, s1, home, away, p, runs=80, wkts=3)})
    _match(conn, wid, comp, s2, home, away, p, runs=120, wkts=2)

    career = player_profile.career_summary(conn, wid, p)
    assert career["matches"] == 2 and career["batting"]["runs"] == 200 and career["bowling"]["wickets"] == 5
    assert career["has_batting"] and career["has_bowling"]
    seasons = player_profile.season_breakdown(conn, wid, p)
    assert len(seasons) == 2
    assert next(s for s in seasons if s["label"] == "2024/25")["runs"] == 120   # seasons not combined
    hist = player_profile.match_history(conn, wid, p)
    assert len(hist) == 2 and hist[0]["runs"] in (80, 120)


def test_unknown_runs_preserved_and_merge_aware(conn):
    wid = _ws(conn, "PP UNK")
    comp = competitions.create_competition(conn, wid, ACTOR, name="L")
    s1 = _season(conn, wid, comp, "2024/25", 2024)
    home, away = _team(conn, wid, "H"), _team(conn, wid, "A")
    canonical = people.create_person(conn, wid, ACTOR, display_name="Canonical")
    dup = people.create_person(conn, wid, ACTOR, display_name="Dup")
    _match(conn, wid, comp, s1, home, away, canonical, runs=50)
    _match(conn, wid, comp, s1, home, away, dup, runs=None)   # unknown runs
    career = player_profile.career_summary(conn, wid, canonical)
    assert career["batting"]["runs"] == 50
    person_resolution.merge_people(conn, wid, ACTOR, canonical_id=canonical, merged_id=dup, reason="same")
    merged = player_profile.career_summary(conn, wid, canonical)
    assert merged["matches"] == 2                                   # merge-aware
    assert merged["batting"]["runs_known_minimum"] is True          # unknown runs -> known-minimum, not 0


def test_full_profile_and_awards_category(conn):
    wid = _ws(conn, "PP FULL")
    comp = competitions.create_competition(conn, wid, ACTOR, name="L")
    s1 = _season(conn, wid, comp, "2024/25", 2024)
    home, away = _team(conn, wid, "H"), _team(conn, wid, "A")
    p = people.create_person(conn, wid, ACTOR, display_name="Star")
    _match(conn, wid, comp, s1, home, away, p, runs=150, wkts=6)
    honours.create_honour(conn, wid, ACTOR, honour_type="club_award", title="Best & Fairest 2024/25",
                          person_id=p, award_category="Best & Fairest", awarded_season="2024/25")
    prof = player_profile.full_profile(conn, wid, p)
    assert prof["career"]["batting"]["runs"] == 150
    assert prof["clubs"] and prof["honours"][0]["award_category"] == "Best & Fairest"
    # holds the Most Runs record
    assert any("Runs" in r["title"] for r in prof["records"])
    # professional profile PDF (shared framework)
    from onestats.core.config import Settings
    from onestats.reports import player_pdf
    pdf = player_pdf.player_profile_pdf(conn, Settings(env="test", db_password=None, _env_file=None), wid, p)
    assert pdf[:5] == b"%PDF-" and len(pdf) > 2500


def test_grand_finals_recorded(conn):
    wid = _ws(conn, "PP GF")
    comp = competitions.create_competition(conn, wid, ACTOR, name="L")
    s1 = _season(conn, wid, comp, "2024/25", 2024)
    home, away = _team(conn, wid, "H"), _team(conn, wid, "A")
    p = people.create_person(conn, wid, ACTOR, display_name="Premiership Captain")
    mid = matches.create_match(conn, wid, ACTOR, competition_id=comp, season_id=s1)
    matches.set_team(conn, wid, ACTOR, mid, team_id=home, is_home=True, captain_person_id=p)
    matches.set_team(conn, wid, ACTOR, mid, team_id=away, is_home=False)
    matches.set_classification(conn, wid, ACTOR, mid, classification="grand_final")
    i1 = inn.create_innings(conn, wid, ACTOR, match_id=mid, inns_number=1, batting_team_id=home, bowling_team_id=away)
    batting.create_entry(conn, wid, ACTOR, innings_id=i1, person_id=p, batting_position=1,
                         runs=92, balls_faced=100, dismissal_type="bowled")
    matches.set_result(conn, wid, ACTOR, mid, result_type="home_win", won_by_team_id=home)
    matches.set_approval(conn, wid, ACTOR, mid, status="approved")

    gf = player_profile.grand_finals(conn, wid, p)
    assert gf["appearances"] == 1 and gf["premierships"] == 1          # team won the grand final (recorded)
    assert gf["batting"]["runs"] == 92 and gf["has_batting"]
    assert gf["captaincy"]["captained"] == 1 and gf["captaincy"]["gf_wins"] == 1
    assert len(gf["matches"]) == 1 and gf["matches"][0]["classification"] == "grand_final"
    assert player_profile.full_profile(conn, wid, p)["grand_finals"]["premierships"] == 1
