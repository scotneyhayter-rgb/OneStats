"""Phase 12, Stage 12.20 — association-scale performance.

Bulk-loads the statistics ledger to association scale (~1,500 matches, ~800 players, ~45k contribution
rows) and asserts the engine's leaderboard and per-person queries, the ladder and a report PDF complete
within generous time budgets. This exercises the indexed query path reports actually use; it is not a
micro-benchmark. Rolled back; skipped without a live DB.
"""
from __future__ import annotations

import json
import time
import uuid

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import Settings, get_settings
from onestats.db.workspace import set_workspace
from onestats.domain.stats import competition_points, engine
from onestats.reports import catalogue

settings = get_settings()
pytestmark = pytest.mark.skipif(not settings.db_configured, reason="no live database credential configured")
ACTOR = "11111111-1111-1111-1111-111111111111"

N_MATCHES = 1500
N_PLAYERS = 800
PER_MATCH_PLAYERS = 12


def _conn():
    eng = create_engine(settings.database_url, future=True)
    c = eng.connect()
    return eng, c


def _seed(conn, wid, comp):
    # real matches (FK target for contributions); two teams for ladder
    home = conn.execute(text("INSERT INTO organisation(workspace_id,name,kind) VALUES (:w,'H CC','club') RETURNING id"),
                        {"w": wid}).scalar_one()
    away = conn.execute(text("INSERT INTO organisation(workspace_id,name,kind) VALUES (:w,'A CC','club') RETURNING id"),
                        {"w": wid}).scalar_one()
    home_t = conn.execute(text("INSERT INTO team(workspace_id,organisation_id,name) VALUES (:w,:o,'Home') RETURNING id"),
                          {"w": wid, "o": home}).scalar_one()
    away_t = conn.execute(text("INSERT INTO team(workspace_id,organisation_id,name) VALUES (:w,:o,'Away') RETURNING id"),
                          {"w": wid, "o": away}).scalar_one()
    match_ids = conn.execute(
        text("INSERT INTO match(workspace_id, competition_id, approval_status, include_in_statistics) "
             "SELECT :w, :c, 'approved', true FROM generate_series(1, :n) RETURNING id"),
        {"w": wid, "c": comp, "n": N_MATCHES},
    ).scalars().all()
    # two match_team rows per match (bulk) for the ladder
    conn.execute(text("INSERT INTO match_team(workspace_id, match_id, team_id, is_home) "
                      "SELECT :w, m, :h, true FROM unnest(CAST(:ids AS uuid[])) m"),
                 {"w": wid, "h": home_t, "ids": match_ids})
    conn.execute(text("INSERT INTO match_team(workspace_id, match_id, team_id, is_home) "
                      "SELECT :w, m, :a, false FROM unnest(CAST(:ids AS uuid[])) m"),
                 {"w": wid, "a": away_t, "ids": match_ids})
    conn.execute(text("UPDATE match SET result_type='home_win', won_by_team_id=:h "
                      "WHERE workspace_id=:w"), {"w": wid, "h": home_t})

    players = [str(uuid.uuid4()) for _ in range(N_PLAYERS)]
    bat, bowl, appr = [], [], []
    for i, m in enumerate(match_ids):
        for j in range(PER_MATCH_PLAYERS):
            pid = players[(i * 7 + j) % N_PLAYERS]
            team = home_t if j % 2 == 0 else away_t
            bat.append({"w": wid, "m": str(m), "sid": pid, "tid": str(team),
                        "met": json.dumps({"innings": 1, "runs": (i + j) % 150, "runs_known": 1, "balls": 60,
                                           "balls_known": 1, "dismissed": 1, "not_out": 0, "hs": (i + j) % 150,
                                           "fifties": 0, "hundreds": 0, "ducks": 0, "fours": 2, "sixes": 0,
                                           "match_runs": (i + j) % 150, "classification": "home_away"})})
            if j < 5:
                bowl.append({"w": wid, "m": str(m), "sid": pid, "tid": str(team),
                             "met": json.dumps({"innings": 1, "balls": 30, "balls_known": 1, "maidens": 1,
                                                "runs": 25, "wickets": j, "wickets_known": 1,
                                                "five_wkt_innings": 0, "bbi_wickets": j, "bbi_runs": 25,
                                                "ten_wkt_match": 0, "match_wickets": j, "classification": "home_away"})})
            appr.append({"w": wid, "m": str(m), "sid": pid, "tid": str(team),
                         "met": json.dumps({"matches": 1, "win": int(j % 2 == 0), "loss": int(j % 2 == 1),
                                            "classification": "home_away"})})

    def _ins(cal, rows):
        conn.execute(
            text("INSERT INTO match_stat_contribution(workspace_id, match_id, calculator, subject_kind, "
                 "subject_id, team_id, metrics) VALUES (:w, :m, :cal, 'person', :sid, :tid, CAST(:met AS jsonb))"),
            [{**r, "cal": cal} for r in rows])

    _ins("player_batting", bat)
    _ins("player_bowling", bowl)
    _ins("player_appearance", appr)
    return players


def test_association_scale_queries_are_fast():
    eng, conn = _conn()
    trans = conn.begin()
    try:
        wid = conn.execute(text("INSERT INTO workspace(name,type) VALUES ('PERF','club') RETURNING id")).scalar_one()
        conn.execute(text("INSERT INTO app_user(id, username) VALUES (:a,'perf') ON CONFLICT (id) DO NOTHING"), {"a": ACTOR})
        set_workspace(conn, wid)
        comp = conn.execute(text("INSERT INTO competition(workspace_id,name) VALUES (:w,'Big League') RETURNING id"),
                            {"w": wid}).scalar_one()
        players = _seed(conn, wid, comp)

        f = {"workspace_id": wid}
        t = time.perf_counter()
        bat = engine.batting_leaders(conn, f, limit=100)
        bat_s = time.perf_counter() - t
        t = time.perf_counter()
        bowl = engine.bowling_leaders(conn, f, limit=100)
        bowl_s = time.perf_counter() - t
        t = time.perf_counter()
        pb = engine.person_batting(conn, f, uuid.UUID(players[0]))
        person_s = time.perf_counter() - t
        t = time.perf_counter()
        lad = competition_points.ladder(conn, wid, competition_id=comp)
        ladder_s = time.perf_counter() - t
        t = time.perf_counter()
        pdf = catalogue.report_pdf(conn, Settings(env="test", db_password=None, _env_file=None), wid, "batting", f)
        pdf_s = time.perf_counter() - t

        assert len(bat) == 100 and bat[0]["runs"] > 0
        assert len(bowl) > 0 and pb["matches"] > 0 and len(lad["standings"]) == 2
        assert pdf[:5] == b"%PDF-"
        # generous budgets: these are indexed aggregate queries over ~45k rows
        assert bat_s < 3.0, f"batting leaderboard too slow: {bat_s:.2f}s"
        assert bowl_s < 3.0, f"bowling leaderboard too slow: {bowl_s:.2f}s"
        assert person_s < 2.0, f"person aggregate too slow: {person_s:.2f}s"
        assert ladder_s < 3.0, f"ladder too slow: {ladder_s:.2f}s"
        assert pdf_s < 5.0, f"report PDF too slow: {pdf_s:.2f}s"
    finally:
        trans.rollback()
        conn.close()
        eng.dispose()
