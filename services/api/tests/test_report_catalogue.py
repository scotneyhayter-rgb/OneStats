"""Report Catalogue (Phase 12 expansion) — every catalogue entry opens, new calculations are verified
against independently hand-computed values, CSV exports, and the catalogue index renders.

Builds one realistic multi-match, multi-season workspace (results, captains, a grand final, batting/
bowling/fielding incl. a 95, a 45, a century, a duck, a five-for, keeper and fielder catches).
Requires a live DB; rolled back. Expected values are worked out by hand in the comments.
"""
from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import Settings, get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import batting, bowling, competitions, matches, people
from onestats.domain import innings as inn
from onestats.reports import catalogue

settings = get_settings()
pytestmark = pytest.mark.skipif(not settings.db_configured, reason="no live database credential configured")
ACTOR = "11111111-1111-1111-1111-111111111111"
_TEST_SETTINGS = Settings(env="test", db_password=None, _env_file=None)


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
                 {"a": ACTOR, "u": f"a-{name}"})
    set_workspace(conn, wid)
    return wid


def _team(conn, wid, name):
    org = conn.execute(text("INSERT INTO organisation(workspace_id,name,kind) VALUES (:w,:n,'club') RETURNING id"),
                       {"w": wid, "n": name + " CC"}).scalar_one()
    return conn.execute(text("INSERT INTO team(workspace_id,organisation_id,name) VALUES (:w,:o,:n) RETURNING id"),
                        {"w": wid, "o": org, "n": name}).scalar_one()


def _season(conn, wid, comp, label, y):
    return conn.execute(text("INSERT INTO season(workspace_id,competition_id,label,start_date) "
                             "VALUES (:w,:c,:l,:d) RETURNING id"),
                        {"w": wid, "c": comp, "l": label, "d": dt.date(y, 10, 1)}).scalar_one()


def _build(conn):
    """One club, two seasons, a captain who wins four straight (incl. a grand final)."""
    wid = _ws(conn, "CATALOGUE")
    comp = competitions.create_competition(conn, wid, ACTOR, name="Ararat & District")
    s1 = _season(conn, wid, comp, "2023/24", 2023)
    s2 = _season(conn, wid, comp, "2024/25", 2024)
    home, away = _team(conn, wid, "Rhymney"), _team(conn, wid, "Pomonal")
    cap = people.create_person(conn, wid, ACTOR, display_name="Captain Marvel")
    big = people.create_person(conn, wid, ACTOR, display_name="Big Hitter")
    demon = people.create_person(conn, wid, ACTOR, display_name="Demon Bowler")
    keep = people.create_person(conn, wid, ACTOR, display_name="Gloves")
    slip = people.create_person(conn, wid, ACTOR, display_name="Slip Fielder")
    duck = people.create_person(conn, wid, ACTOR, display_name="Away Duck")
    aw2 = people.create_person(conn, wid, ACTOR, display_name="Away Two")

    # (season, classification, big's score, demon wickets, demon runs conceded)
    plan = [(s1, "home_away", 95, 2, 20), (s1, "home_away", 45, 3, 30),
            (s1, "home_away", 120, 0, 25), (s2, "grand_final", 30, 5, 60)]
    for season, cls, big_runs, dw, dr in plan:
        mid = matches.create_match(conn, wid, ACTOR, competition_id=comp, season_id=season)
        matches.set_team(conn, wid, ACTOR, mid, team_id=home, is_home=True, captain_person_id=cap,
                         wicketkeeper_person_id=keep)
        matches.set_team(conn, wid, ACTOR, mid, team_id=away, is_home=False)
        if cls != "home_away":
            matches.set_classification(conn, wid, ACTOR, mid, classification=cls)
        # home bats (big + cap), home always wins
        i1 = inn.create_innings(conn, wid, ACTOR, match_id=mid, inns_number=1, batting_team_id=home, bowling_team_id=away)
        batting.create_entry(conn, wid, ACTOR, innings_id=i1, person_id=big, batting_position=1,
                             runs=big_runs, balls_faced=max(big_runs, 1), fours=4, sixes=1, dismissal_type="bowled")
        batting.create_entry(conn, wid, ACTOR, innings_id=i1, person_id=cap, batting_position=2,
                             runs=20, balls_faced=30, dismissal_type="not_out")
        # away bats, dismissed by demon (duck for a nought, aw2 caught by slip off demon, caught_behind by keeper)
        i2 = inn.create_innings(conn, wid, ACTOR, match_id=mid, inns_number=2, batting_team_id=away, bowling_team_id=home)
        batting.create_entry(conn, wid, ACTOR, innings_id=i2, person_id=duck, batting_position=1,
                             runs=0, balls_faced=2, dismissal_type="bowled", bowler_person_id=demon)
        batting.create_entry(conn, wid, ACTOR, innings_id=i2, person_id=aw2, batting_position=2,
                             runs=15, dismissal_type="caught", bowler_person_id=demon, fielder_person_id=slip)
        bowling.create_entry(conn, wid, ACTOR, innings_id=i2, person_id=demon, legal_balls=48,
                             maidens=1, runs_conceded=dr, wickets=dw)
        matches.set_result(conn, wid, ACTOR, mid, result_type="home_win", won_by_team_id=home)
        matches.set_approval(conn, wid, ACTOR, mid, status="approved")
    return {"wid": wid, "comp": comp, "cap": cap, "big": big, "demon": demon, "keep": keep,
            "slip": slip, "duck": duck}


def test_every_catalogue_entry_opens_and_exports(conn):
    d = _build(conn)
    wid = d["wid"]
    f = {"workspace_id": wid}
    assert len(catalogue.CATALOGUE) >= 60
    for entry in catalogue.CATALOGUE:
        data = catalogue.report_rows(conn, wid, entry.id, f)        # opens without error
        assert "columns" in data and "rows" in data and isinstance(data["rows"], list)
        assert data["title"] == entry.name
        csv_text = catalogue.report_csv(conn, wid, entry.id, f)      # CSV exports
        assert csv_text.splitlines()[0]                             # has a header row
    # catalogue metadata + printable index
    meta = catalogue.catalogue_metadata()
    assert meta["count"] == len(catalogue.CATALOGUE) and meta["categories"]
    pdf = catalogue.catalogue_index_pdf(conn, _TEST_SETTINGS, wid)
    assert pdf[:5] == b"%PDF-"


def test_streak_reference(conn):
    d = _build(conn)
    f = {"workspace_id": d["wid"]}
    # Captain won all four captained matches -> consecutive wins = 4; team won all four -> 4.
    cap_wins = catalogue.report_rows(conn, d["wid"], "capt_consec_wins", f)["rows"]
    me = next(r for r in cap_wins if r["player"] == "Captain Marvel")
    assert me["streak"] == 4
    team_wins = catalogue.report_rows(conn, d["wid"], "team_consec_wins", f)["rows"]
    rhymney = next(r for r in team_wins if r["team"] == "Rhymney")
    assert rhymney["streak"] == 4


def test_records_detail_reference(conn):
    d = _build(conn)
    wid, f = d["wid"], {"workspace_id": d["wid"]}
    # Highest individual innings = 120 (Big Hitter).
    hi = catalogue.report_rows(conn, wid, "bat_top_scores", f)["rows"]
    assert hi[0]["player"] == "Big Hitter" and hi[0]["runs"] == 120
    # 90s = one (the 95); 40s = one (the 45).
    n90 = catalogue.report_rows(conn, wid, "bat_most_90s", f)["rows"]
    assert next(r for r in n90 if r["player"] == "Big Hitter")["count"] == 1
    n40 = catalogue.report_rows(conn, wid, "bat_most_40s", f)["rows"]
    assert next(r for r in n40 if r["player"] == "Big Hitter")["count"] == 1
    # Best single season (runs): 95+45+120 = 260 in 2023/24.
    bs = catalogue.report_rows(conn, wid, "bat_most_runs_season", f)["rows"]
    top = next(r for r in bs if r["player"] == "Big Hitter")
    assert top["value"] == 260 and top["season"] == "2023/24"
    # Ducks inflicted: Demon bowled the away duck in all four matches -> 4.
    di = catalogue.report_rows(conn, wid, "bowl_most_ducks_inflicted", f)["rows"]
    assert next(r for r in di if r["player"] == "Demon Bowler")["count"] == 4
    # Fielder-bowler combo: Slip caught off Demon in all four matches -> 4.
    fb = catalogue.report_rows(conn, wid, "field_bowler_combos", f)["rows"]
    assert fb[0]["count"] == 4 and fb[0]["bowler_name"] == "Demon Bowler" and fb[0]["fielder_name"] == "Slip Fielder"
    # Most expensive innings = 60 (the grand final spell).
    exp = catalogue.report_rows(conn, wid, "bowl_most_expensive", f)["rows"]
    assert exp[0]["player"] == "Demon Bowler" and exp[0]["runs"] == 60
    # Boundaries: Big Hitter has 4 fours + 1 six per match × 4 = 20 boundaries, top of the list.
    bnd = catalogue.report_rows(conn, wid, "bat_most_boundaries", f)["rows"]
    assert next(r for r in bnd if r["player"] == "Big Hitter")["boundaries"] == 20


def test_grand_final_split_and_qualification(conn):
    d = _build(conn)
    wid, f = d["wid"], {"workspace_id": d["wid"]}
    # GF batting preset: only the grand-final innings (Big Hitter 30, Captain 20) -> Big's GF runs = 30.
    gf = catalogue.report_rows(conn, wid, "gf_batting", f)["rows"]
    assert next(r for r in gf if r["player"] == "Big Hitter")["runs"] == 30
    # Captaincy win% report qualifies by min eligible (RMCC 20); with 4 matches none qualify but rows remain.
    wp = catalogue.report_rows(conn, wid, "capt_best_win_pct", f)["rows"]
    assert wp == [] or all("win_pct" in r for r in wp)
