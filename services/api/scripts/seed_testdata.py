"""OneStats synthetic test-data seed (safe, repeatable).

Creates ONE clearly-named workspace of synthetic cricket data for manual/automated testing, then
can tear it down. It ONLY ever touches workspaces named exactly ``SEED_WS_NAME`` — it never resets
the database and never alters real historical records or any other workspace.

Usage (from services/api, with the venv python):
    .venv\\Scripts\\python scripts\\seed_testdata.py            # create (idempotent: tears down first)
    .venv\\Scripts\\python scripts\\seed_testdata.py --teardown  # remove the synthetic workspace only

Includes: two clubs & teams, a competition/grade, two seasons, registered + fill-in players, a
complete scorecard (batting, bowling, FOW, partnerships) with a retirement and a DELIBERATE known
inconsistency, and an incomplete historical match — enough to exercise dropdowns, participation,
partnerships, calculations and validation.
"""
from __future__ import annotations

import datetime as dt
import sys

from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import (
    affiliations,
    batting,
    bowling,
    competitions,
    matches,
    partnerships,
    people,
)
from onestats.domain import innings as inn

SEED_WS_NAME = "ONESTATS SYNTHETIC TEST"
ACTOR = "11111111-1111-1111-1111-111111111111"
s = get_settings()


def _teardown(su) -> int:
    """Delete only the synthetic workspace(s). FORCE RLS means we must set the GUC to clear audit."""
    removed = 0
    with su.connect() as c:
        ids = list(c.execute(text("SELECT id FROM workspace WHERE name = :n"), {"n": SEED_WS_NAME}).scalars())
    for wid in ids:
        with su.connect() as c:
            t = c.begin()
            set_workspace(c, wid)
            c.execute(text("DELETE FROM audit_log WHERE workspace_id = :w"), {"w": wid})
            c.execute(text("DELETE FROM workspace WHERE id = :w"), {"w": wid})  # CASCADE clears the rest
            t.commit()
            removed += 1
    return removed


def _org(c, wid, name):
    return c.execute(text("INSERT INTO organisation(workspace_id,name,kind) VALUES (:w,:n,'club') RETURNING id"),
                     {"w": wid, "n": name}).scalar_one()


def _team(c, wid, org, name):
    return c.execute(text("INSERT INTO team(workspace_id,organisation_id,name) VALUES (:w,:o,:n) RETURNING id"),
                     {"w": wid, "o": org, "n": name}).scalar_one()


def _season(c, wid, cid, label, sf, st):
    return c.execute(
        text("INSERT INTO season(workspace_id,competition_id,label,start_date,end_date) "
             "VALUES (:w,:c,:l,:sf,:st) RETURNING id"),
        {"w": wid, "c": cid, "l": label, "sf": sf, "st": st},
    ).scalar_one()


def _seed(app) -> dict:
    with app.connect() as c:
        t = c.begin()
        wid = c.execute(text("INSERT INTO workspace(name,type) VALUES (:n,'club') RETURNING id"),
                        {"n": SEED_WS_NAME}).scalar_one()
        set_workspace(c, wid)
        cid = competitions.create_competition(c, wid, ACTOR, name="RDCA")
        grade = c.execute(text("INSERT INTO grade(workspace_id,competition_id,name) VALUES (:w,:c,'A Grade') RETURNING id"),
                          {"w": wid, "c": cid}).scalar_one()
        s25 = _season(c, wid, cid, "2025/26", dt.date(2025, 10, 1), dt.date(2026, 3, 31))
        s26 = _season(c, wid, cid, "2026/27", dt.date(2026, 10, 1), dt.date(2027, 3, 31))

        sandbox = _org(c, wid, "Sandbox Cricket Club")
        testvalley = _org(c, wid, "Test Valley Cricket Club")
        sbx = _team(c, wid, sandbox, "Sandbox 1st XI")
        tvx = _team(c, wid, testvalley, "Test Valley 1st XI")

        # players: registered to Sandbox + a fill-in (Bill), plus Test Valley players
        reg = {}
        for n in ("A. Opener", "B. Partner", "C. Allrounder", "D. Keeper"):
            pid = people.create_person(c, wid, ACTOR, display_name=n)
            affiliations.create_affiliation(c, wid, ACTOR, person_id=pid, organisation_id=sandbox,
                                             team_id=sbx, role="player", valid_from=dt.date(2020, 9, 1))
            reg[n] = pid
        bill = people.create_person(c, wid, ACTOR, display_name="Bill Smith")
        affiliations.create_affiliation(c, wid, ACTOR, person_id=bill, organisation_id=sandbox, team_id=sbx,
                                         role="player", valid_from=dt.date(2019, 9, 1))  # registered Sandbox
        tv_players = {n: people.create_person(c, wid, ACTOR, display_name=n)
                      for n in ("TV Opener", "TV Two", "TV Bowler")}

        # --- COMPLETE match: Test Valley v Sandbox, 2026/27; Bill fills in for Test Valley ---
        m1 = matches.create_match(c, wid, ACTOR, competition_id=cid, grade_id=grade, season_id=s26,
                                  match_date=dt.date(2026, 11, 14), round="Round 5", format="two-day")
        matches.set_team(c, wid, ACTOR, m1, team_id=tvx, is_home=True, captain_person_id=tv_players["TV Opener"],
                         wicketkeeper_person_id=tv_players["TV Two"])
        matches.set_team(c, wid, ACTOR, m1, team_id=sbx, is_home=False, captain_person_id=reg["C. Allrounder"],
                         wicketkeeper_person_id=reg["D. Keeper"])
        matches.set_toss(c, wid, ACTOR, m1, toss_winner_team_id=tvx, toss_decision="bat")
        # Bill fills in for Test Valley -> TEMPORARY affiliation (registration unchanged)
        affiliations.create_affiliation(c, wid, ACTOR, person_id=bill, organisation_id=testvalley, team_id=tvx,
                                         role="player", is_temporary=True, valid_from=dt.date(2026, 10, 1),
                                         valid_to=dt.date(2027, 3, 31), notes="fill-in")
        # innings 1: Test Valley batting (Bill 45*), with FOW + a retirement partnership
        i1 = inn.create_innings(c, wid, ACTOR, match_id=m1, inns_number=1, batting_team_id=tvx, bowling_team_id=sbx,
                                status="completed", byes=4, legbyes=2)
        be_bill = batting.create_entry(c, wid, ACTOR, innings_id=i1, person_id=bill, batting_position=1, runs=45,
                                       fours=5, dismissal_type="not_out")
        batting.create_entry(c, wid, ACTOR, innings_id=i1, person_id=tv_players["TV Opener"], batting_position=2,
                             runs=30, dismissal_type="caught", bowler_person_id=reg["C. Allrounder"])
        batting.create_entry(c, wid, ACTOR, innings_id=i1, person_id=tv_players["TV Two"], batting_position=3,
                             runs=None, dismissal_type="retired_not_out", evidence="retired hurt, The Argus")
        bowling.create_entry(c, wid, ACTOR, innings_id=i1, person_id=reg["C. Allrounder"], bowling_order=1,
                             overs_text="10.3", maidens=2, runs_conceded=40, wickets=1)
        partnerships.create_fow(c, wid, ACTOR, innings_id=i1, wicket_number=1, team_score=78,
                               dismissed_person_id=tv_players["TV Opener"])
        partnerships.create_partnership(c, wid, ACTOR, innings_id=i1, wicket_number=1, runs=78,
                                       player1_person_id=bill, player2_person_id=tv_players["TV Opener"],
                                       end_reason="wicket")
        partnerships.create_partnership(c, wid, ACTOR, innings_id=i1, wicket_number=2, runs=20,
                                       player1_person_id=bill, end_reason="retired")  # retirement 2nd stand
        # DELIBERATE known inconsistency: official total below what the card supports (for validation testing)
        inn.set_official_total(c, wid, ACTOR, i1, total=60, wickets=1, reason="synthetic inconsistency for testing")
        # innings 2: Sandbox batting, Test Valley bowling (Bill 2 wkts, 1 catch)
        i2 = inn.create_innings(c, wid, ACTOR, match_id=m1, inns_number=2, batting_team_id=sbx, bowling_team_id=tvx,
                                status="completed")
        bowling.create_entry(c, wid, ACTOR, innings_id=i2, person_id=bill, bowling_order=1, overs_text="8",
                             maidens=1, runs_conceded=22, wickets=2)
        batting.create_entry(c, wid, ACTOR, innings_id=i2, person_id=reg["A. Opener"], batting_position=1, runs=12,
                             dismissal_type="caught", fielder_person_id=bill, bowler_person_id=tv_players["TV Bowler"])
        matches.set_classification(c, wid, ACTOR, m1, classification="home_away")
        matches.set_result(c, wid, ACTOR, m1, result_type="home_win", won_by_team_id=tvx, margin_runs=25)

        # --- INCOMPLETE historical match: only a result + lineup, no ball-by-ball (2025/26) ---
        m2 = matches.create_match(c, wid, ACTOR, competition_id=cid, grade_id=grade, season_id=s25,
                                  match_date=dt.date(2025, 12, 6), date_precision="approx", round="Round 3",
                                  status="draft")
        matches.set_team(c, wid, ACTOR, m2, team_id=sbx, is_home=True)
        matches.set_team(c, wid, ACTOR, m2, team_id=tvx, is_home=False)
        inn.create_innings(c, wid, ACTOR, match_id=m2, inns_number=1, batting_team_id=sbx, bowling_team_id=tvx,
                          status="incomplete")  # unknown everything — a legitimate partial record

        t.commit()
        return {"workspace_id": str(wid), "complete_match": str(m1), "incomplete_match": str(m2),
                "bill_smith": str(bill), "test_valley_team": str(tvx), "sandbox_team": str(sbx),
                "batting_entry_bill": str(be_bill)}


def main() -> int:
    if not s.db_configured:
        print("No database configured — set credentials first.")
        return 1
    app = create_engine(s.database_url, future=True)
    su = create_engine(s.migration_url, future=True)
    teardown_only = "--teardown" in sys.argv
    n = _teardown(su)  # always start clean (idempotent)
    if teardown_only:
        print(f"Removed {n} synthetic workspace(s) named {SEED_WS_NAME!r}.")
        return 0
    info = _seed(app)
    print("Seeded synthetic test data (safe — only the synthetic workspace was touched):")
    for k, v in info.items():
        print(f"  {k}: {v}")
    print(f"\nWorkspace name: {SEED_WS_NAME!r}")
    print("Tear down later with:  python scripts\\seed_testdata.py --teardown")
    app.dispose()
    su.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
