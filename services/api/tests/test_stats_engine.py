"""Phase 12, Stage 12.1-12.11 — deterministic statistics engine over the approved ledger.

A rich approved match exercises batting (HS/50s/100s/ducks/avg/SR + unknown balls), bowling (5-for/BBI/
economy with over length), fielding/WK (catch vs keeper-catch vs stumping vs run-out), captaincy
(win%/eligible/GF), participation and team results, plus classification splits. Rolled back; skipped
without a live DB.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import batting, bowling, competitions, matches, people, recalc
from onestats.domain import innings as inn
from onestats.domain.stats import engine, integrity, reconciliation

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


def _p(conn, wid, name):
    return people.create_person(conn, wid, ACTOR, display_name=name)


def _build(conn, wid, *, classification="grand_final"):
    cid = competitions.create_competition(conn, wid, ACTOR, name="League")
    home, away = _team(conn, wid, "Home"), _team(conn, wid, "Away")
    bat1, bat2, bat3, bat4, bat5 = (_p(conn, wid, n) for n in ("Hundred Maker", "Fifty", "Duck", "Runout", "Stumped"))
    bowler, fielder, fielder2, keeper = (_p(conn, wid, n) for n in ("Bowler", "Catcher", "Throwerouter", "Keeper"))
    mid = matches.create_match(conn, wid, ACTOR, competition_id=cid)
    matches.set_team(conn, wid, ACTOR, mid, team_id=home, is_home=True, captain_person_id=bat1)
    matches.set_team(conn, wid, ACTOR, mid, team_id=away, is_home=False, captain_person_id=bowler,
                     wicketkeeper_person_id=keeper)
    i1 = inn.create_innings(conn, wid, ACTOR, match_id=mid, inns_number=1, batting_team_id=home, bowling_team_id=away)
    batting.create_entry(conn, wid, ACTOR, innings_id=i1, person_id=bat1, batting_position=1,
                         runs=120, balls_faced=90, fours=12, sixes=2, dismissal_type="not_out")
    batting.create_entry(conn, wid, ACTOR, innings_id=i1, person_id=bat2, batting_position=2,
                         runs=55, balls_faced=None, dismissal_type="bowled", bowler_person_id=bowler)  # unknown balls
    batting.create_entry(conn, wid, ACTOR, innings_id=i1, person_id=bat3, batting_position=3,
                         runs=0, balls_faced=3, dismissal_type="caught", bowler_person_id=bowler, fielder_person_id=fielder)
    batting.create_entry(conn, wid, ACTOR, innings_id=i1, person_id=bat4, batting_position=4,
                         runs=10, balls_faced=12, dismissal_type="run_out", fielder_person_id=fielder2)
    batting.create_entry(conn, wid, ACTOR, innings_id=i1, person_id=bat5, batting_position=5,
                         runs=20, balls_faced=18, dismissal_type="stumped", bowler_person_id=bowler, fielder_person_id=keeper)
    bowling.create_entry(conn, wid, ACTOR, innings_id=i1, person_id=bowler, legal_balls=30, maidens=1,
                         runs_conceded=20, wickets=5)
    matches.set_result(conn, wid, ACTOR, mid, result_type="home_win", won_by_team_id=home)
    if classification:
        matches.set_classification(conn, wid, ACTOR, mid, classification=classification)
    matches.set_approval(conn, wid, ACTOR, mid, status="approved")
    return {"mid": mid, "home": home, "away": away, "bat1": bat1, "bat2": bat2, "bat3": bat3,
            "bat4": bat4, "bat5": bat5, "bowler": bowler, "fielder": fielder, "fielder2": fielder2, "keeper": keeper}


def _f(wid, **kw):
    return {"workspace_id": wid, **kw}


def test_batting_engine(conn):
    wid = _ws(conn, "ENG BAT")
    x = _build(conn, wid)
    lead = {r["subject_id"]: r for r in engine.batting_leaders(conn, _f(wid))}
    b1 = lead[str(x["bat1"])]
    assert b1["runs"] == 120 and b1["hundreds"] == 1 and b1["highest_score"] == 120
    assert b1["not_outs"] == 1 and b1["dismissed"] == 0 and b1["average"] is None   # never out
    b2 = lead[str(x["bat2"])]
    assert b2["runs"] == 55 and b2["fifties"] == 1 and b2["dismissed"] == 1
    assert b2["balls_incomplete"] is True and b2["strike_rate"] is None             # unknown balls, not zero
    b3 = lead[str(x["bat3"])]
    assert b3["ducks"] == 1 and b3["average"] == 0.0


def test_bowling_engine(conn):
    wid = _ws(conn, "ENG BOWL")
    x = _build(conn, wid)
    row = next(r for r in engine.bowling_leaders(conn, _f(wid), over_length=6) if r["subject_id"] == str(x["bowler"]))
    assert row["wickets"] == 5 and row["five_wkt_innings"] == 1 and row["best_match_wickets"] == 5
    assert row["average"] == 4.0 and row["economy"] == 4.0 and row["strike_rate"] == 6.0


def test_fielding_engine(conn):
    wid = _ws(conn, "ENG FIELD")
    x = _build(conn, wid)
    lead = {r["subject_id"]: r for r in engine.fielding_leaders(conn, _f(wid))}
    assert lead[str(x["fielder"])]["field_catches"] == 1 and lead[str(x["fielder"])]["catches"] == 1
    assert lead[str(x["fielder2"])]["run_outs"] == 1
    k = lead[str(x["keeper"])]
    assert k["stumpings"] == 1 and k["keeper_dismissals"] == 1 and k["field_catches"] == 0


def test_multi_fielder_run_out_credits_assist_without_changing_primary(conn):
    """R-3: a second fielder in a run-out is credited a distinct run_out ASSIST; the primary fielder's
    run_outs is unchanged, and the dismissal is still one wicket (no double count)."""
    wid = _ws(conn, "ENG R3")
    x = _build(conn, wid)
    # the run-out entry (bat4), primary fielder = fielder2; credit 'fielder' (the catcher) as the thrower
    eid = conn.execute(text("SELECT id FROM batting_entry WHERE dismissal_type = 'run_out'"
                            " AND fielder_person_id = :f"), {"f": x["fielder2"]}).scalar_one()
    batting.set_run_out_fielders(conn, wid, ACTOR, eid, [{"person_id": str(x["fielder"]), "role": "thrower"}])
    recalc.recompute_match(conn, wid, ACTOR, x["mid"])

    lead = {r["subject_id"]: r for r in engine.fielding_leaders(conn, _f(wid))}
    primary, assist = lead[str(x["fielder2"])], lead[str(x["fielder"])]
    # primary unchanged; assist credited separately; involvements combine the two
    assert primary["run_outs"] == 1 and primary["run_out_assists"] == 0 and primary["run_out_involvements"] == 1
    assert assist["run_outs"] == 0 and assist["run_out_assists"] == 1 and assist["run_out_involvements"] == 1
    # the fielder also keeps their catch — assist is additive, not a reclassification
    assert assist["field_catches"] == 1
    # reconciliation still sees exactly one run-out wicket (no double count)
    from onestats.domain.stats import reconciliation
    assert reconciliation.reconcile_match(conn, wid, x["mid"])["total_run_outs"] == 1

    # changing the dismissal away from run_out clears the assisting fielders
    batting.update_entry(conn, wid, ACTOR, eid, dismissal_type="bowled", fielder_person_id=None)
    assert batting.list_dismissal_fielders(conn, eid) == []


def test_set_run_out_fielders_rejects_non_run_out_and_primary(conn):
    wid = _ws(conn, "ENG R3 GUARD")
    x = _build(conn, wid)
    caught = conn.execute(text("SELECT id FROM batting_entry WHERE dismissal_type = 'caught'")).scalar_one()
    with pytest.raises(ValueError, match="not_a_run_out"):
        batting.set_run_out_fielders(conn, wid, ACTOR, caught, [{"person_id": str(x["fielder"])}])
    run_out = conn.execute(text("SELECT id FROM batting_entry WHERE dismissal_type = 'run_out'")).scalar_one()
    # the primary fielder and duplicates are ignored (never double-credited)
    out = batting.set_run_out_fielders(conn, wid, ACTOR, run_out,
                                       [{"person_id": str(x["fielder2"])},
                                        {"person_id": str(x["fielder"])},
                                        {"person_id": str(x["fielder"])}])
    assert [f["person_id"] for f in out] == [str(x["fielder"])]


def test_captaincy_and_team_engine(conn):
    wid = _ws(conn, "ENG CAPT")
    x = _build(conn, wid)
    caps = {r["subject_id"]: r for r in engine.captaincy_leaders(conn, _f(wid), min_eligible=1)}
    c1 = caps[str(x["bat1"])]
    assert c1["captained"] == 1 and c1["wins"] == 1 and c1["eligible"] == 1 and c1["win_pct"] == 100.0
    assert c1["gf_captained"] == 1 and c1["gf_wins"] == 1 and c1["qualified"] is True
    teams = {r["subject_id"]: r for r in engine.team_records(conn, _f(wid))}
    assert teams[str(x["home"])]["wins"] == 1 and teams[str(x["away"])]["losses"] == 1


def test_classification_split_filters(conn):
    wid = _ws(conn, "ENG SPLIT")
    _build(conn, wid, classification="grand_final")
    # grand-final split includes the match; home_away split excludes it
    assert len(engine.batting_leaders(conn, _f(wid, split="grand_final"))) > 0
    assert engine.batting_leaders(conn, _f(wid, split="home_away")) == []


def test_run_out_reconciliation(conn):
    wid = _ws(conn, "ENG RECON")
    x = _build(conn, wid)
    # 5 batters: not_out (no wicket), bowled, caught, run_out, stumped -> 3 bowler + 1 run out = 4 wickets
    conn.execute(text("UPDATE innings SET official_wickets = 4 WHERE match_id = :m"), {"m": x["mid"]})
    rep = reconciliation.reconcile_match(conn, wid, x["mid"])
    inn0 = rep["innings"][0]
    assert inn0["bowler_credited"] == 3 and inn0["run_outs"] == 1 and inn0["other_non_bowler_wickets"] == 0
    assert inn0["wickets_from_dismissals"] == 4 and inn0["status"] == "reconciled"
    assert rep["total_run_outs"] == 1 and rep["ok"] is True
    # a mismatch is warned, never auto-corrected
    conn.execute(text("UPDATE innings SET official_wickets = 6 WHERE match_id = :m"), {"m": x["mid"]})
    rep2 = reconciliation.reconcile_match(conn, wid, x["mid"])
    assert rep2["innings"][0]["status"] == "mismatch" and rep2["innings"][0]["warnings"]
    # unrecorded wickets -> insufficient, not invented
    conn.execute(text("UPDATE innings SET official_wickets = NULL WHERE match_id = :m"), {"m": x["mid"]})
    assert reconciliation.reconcile_match(conn, wid, x["mid"])["innings"][0]["status"] == "insufficient"


def test_data_integrity_report(conn):
    wid = _ws(conn, "ENG INTEG")
    x = _build(conn, wid)
    conn.execute(text("UPDATE innings SET official_wickets = 6 WHERE match_id = :m"), {"m": x["mid"]})  # mismatch (4 real)
    rep = integrity.workspace_integrity(conn, wid)
    assert rep["approved_matches"] == 1 and rep["reconciliation_mismatches"] == 1 and rep["ok"] is False
    # bat2 had unknown balls faced -> flagged as unknown-data, never zero
    assert rep["contributions_with_unknown_batting_balls"] >= 1


def test_participation_and_only_approved(conn):
    wid = _ws(conn, "ENG PART")
    x = _build(conn, wid)
    part = {r["subject_id"]: r for r in engine.participation_leaders(conn, _f(wid))}
    assert part[str(x["bat1"])]["matches"] == 1 and part[str(x["bat1"])]["wins"] == 1
    # a draft match contributes nothing
    mid2 = matches.create_match(conn, wid, ACTOR)
    assert recalc.recompute_match(conn, wid, ACTOR, mid2)["contributions"] == 0
