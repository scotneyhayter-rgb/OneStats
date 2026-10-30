"""Automatic recalculation framework (Phase 7, Stage 7.8).

A reusable, idempotent engine that maintains the official-statistics ledger
(``match_stat_contribution``). A match's contributions are (re)computed only while it is an
**approved**, statistics-eligible scorecard; recomputing a match **replaces** its rows, so repeated
recalculation never double counts. Because contributions are written at approval time and left
untouched by later edits, official statistics keep the last approved version until a revision is
re-approved. Non-official matches (draft/awaiting/rejected, or excluded from statistics) contribute
nothing. Deleting a match removes its contributions (ON DELETE CASCADE), so duplicate removal is
handled automatically.

Calculators are registered in ``CALCULATORS``; each maps an approved match to a list of per-subject
contributions. Future statistics, records, milestones, competition points and AutoSync register
more calculators against the same ledger — this module is the integration point, not the full
reporting modules. Two concrete calculators ship now: player batting and player bowling.

Aggregation is **merge-aware**: totals for a person include contributions recorded against any
identity merged into them, so correcting an identity combines the statistics without re-import.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain import audit, matches
from onestats.domain.batting import NON_WICKET_STATUSES

_NON_WICKET = ", ".join(f"'{s}'" for s in NON_WICKET_STATUSES)
_DID_NOT_BAT = ("dnb", "absent")


def _match_scope(match: dict[str, Any]) -> dict[str, Any]:
    return {"season_id": match.get("season_id"), "grade_id": match.get("grade_id"),
            "competition_id": match.get("competition_id")}


# --- match context shared by all calculators (home/away, classification, per-team result, keepers) ---

def _home_away(conn: Connection, match_id: UUID) -> tuple[Any, Any]:
    """(home_team_id, away_team_id) for the match, or (None, None) when not recorded."""
    rows = conn.execute(
        text("SELECT team_id, is_home FROM match_team WHERE match_id = :m"), {"m": match_id}
    ).mappings().all()
    home = next((r["team_id"] for r in rows if r["is_home"] is True), None)
    away = next((r["team_id"] for r in rows if r["is_home"] is False), None)
    return home, away


def _team_result(match: dict[str, Any], team_id: Any, home_id: Any) -> str:
    """This team's result in the match: win|loss|tie|draw|no_result|unknown. A defined-winner forfeit
    counts as win/loss (per the documented default); abandoned/washout/no_result are no_result; unknown
    stays unknown (never assumed)."""
    rt = match.get("result_type")
    won_by = match.get("won_by_team_id")
    if rt in ("home_win", "away_win", "forfeit"):
        if won_by is None:
            return "unknown"
        return "win" if str(team_id) == str(won_by) else "loss"
    if rt == "tie":
        return "tie"
    if rt == "draw":
        return "draw"
    if rt in ("no_result", "abandoned", "washout"):
        return "no_result"
    return "unknown"


def _is_grand_final(match: dict[str, Any]) -> bool:
    return match.get("classification") == "grand_final" or match.get("finals_stage") == "grand_final"


def _forfeit_no_play(conn: Connection, match: dict[str, Any]) -> bool:
    """A forfeit/awarded match in which no cricket was played — detected by the absence of any batting or
    bowling entries (approved forfeit policy, deliverable 24 §24.2a). Such a match still yields a TEAM
    result (and competition points) but must NOT create individual player or captaincy appearances, nor
    inflate wins/losses/streaks/winning-percentage. A partly-played match that was later awarded keeps its
    recorded entries, so it is not treated as no-play."""
    if match.get("result_type") != "forfeit":
        return False
    played = conn.execute(
        text("SELECT 1 FROM innings i WHERE i.match_id = :m AND ("
             "  EXISTS (SELECT 1 FROM batting_entry be WHERE be.innings_id = i.id) OR "
             "  EXISTS (SELECT 1 FROM bowling_entry bo WHERE bo.innings_id = i.id)) LIMIT 1"),
        {"m": match["id"]},
    ).first()
    return played is None


def _keepers_by_team(conn: Connection, match_id: UUID) -> dict[str, set]:
    """Wicketkeeper person ids per team for the match (for keeper-catch classification)."""
    out: dict[str, set] = {}
    for r in conn.execute(
        text("SELECT team_id, wicketkeeper_person_id, wicketkeeper2_person_id FROM match_team WHERE match_id = :m"),
        {"m": match_id},
    ).mappings().all():
        keepers = {str(r[k]) for k in ("wicketkeeper_person_id", "wicketkeeper2_person_id") if r[k] is not None}
        out[str(r["team_id"])] = keepers
    return out


def _calc_player_batting(conn: Connection, match: dict[str, Any]) -> list[dict[str, Any]]:
    """One batting contribution per person in the match. Per-innings figures (highest score, fifties,
    hundreds, ducks) are derived here so career/season aggregates can sum them without re-reading raw
    scorecards. ``balls`` is summed only where recorded (a missing balls-faced is unknown, not zero —
    callers compute strike rate only over recorded balls)."""
    rows = conn.execute(
        text(
            "SELECT be.person_id AS pid, be.runs AS runs, be.balls_faced AS balls, "
            " coalesce(be.fours,0) AS fours, coalesce(be.sixes,0) AS sixes, be.dismissal_type AS dt, "
            " i.batting_team_id AS team_id "
            "FROM batting_entry be JOIN innings i ON i.id = be.innings_id "
            "WHERE i.match_id = :m AND be.person_id IS NOT NULL "
            "  AND (be.dismissal_type IS NULL OR be.dismissal_type NOT IN ('dnb','absent'))"
        ),
        {"m": match["id"]},
    ).mappings().all()
    home, _ = _home_away(conn, match["id"])
    gf = _is_grand_final(match)
    cls = match.get("classification")
    agg: dict[Any, dict[str, Any]] = {}
    for r in rows:
        a = agg.setdefault(r["pid"], {"team_id": r["team_id"], "innings": 0, "runs": 0, "runs_known": 0,
                                      "balls": 0, "balls_known": 0, "runs_with_balls": 0,
                                      "fours": 0, "sixes": 0, "dismissed": 0,
                                      "not_out": 0, "hs": None, "fifties": 0, "hundreds": 0, "ducks": 0})
        runs = r["runs"] or 0
        dismissed = r["dt"] is not None and r["dt"] not in NON_WICKET_STATUSES
        a["innings"] += 1
        a["runs"] += runs
        if r["runs"] is not None:
            a["runs_known"] += 1
        a["fours"] += r["fours"]
        a["sixes"] += r["sixes"]
        if r["balls"] is not None:
            a["balls"] += r["balls"]
            a["balls_known"] += 1
            # strike rate is over recorded balls only, so its numerator is the runs from those same innings
            a["runs_with_balls"] += runs
        if dismissed:
            a["dismissed"] += 1
        if r["dt"] in ("not_out", "retired_not_out"):
            a["not_out"] += 1
        if r["runs"] is not None:
            a["hs"] = runs if a["hs"] is None else max(a["hs"], runs)
            if runs >= 100:
                a["hundreds"] += 1
            elif runs >= 50:
                a["fifties"] += 1
            if runs == 0 and dismissed:
                a["ducks"] += 1
    out = []
    for pid, a in agg.items():
        if a["innings"] == 0:
            continue
        out.append({"subject_kind": "person", "subject_id": pid, "team_id": a["team_id"], **_match_scope(match),
                    "metrics": {"innings": a["innings"], "runs": a["runs"], "runs_known": a["runs_known"],
                                "balls": a["balls"], "balls_known": a["balls_known"],
                                "runs_with_balls": a["runs_with_balls"], "fours": a["fours"],
                                "sixes": a["sixes"], "dismissed": a["dismissed"], "not_out": a["not_out"], "hs": a["hs"],
                                "fifties": a["fifties"], "hundreds": a["hundreds"], "ducks": a["ducks"],
                                "match_runs": a["runs"],
                                "is_home": str(a["team_id"]) == str(home) if home else None,
                                "classification": cls, "grand_final": gf}})
    return out


def _calc_player_bowling(conn: Connection, match: dict[str, Any]) -> list[dict[str, Any]]:
    """One bowling contribution per person in the match. Per-innings best bowling (BBI) and five-wicket
    innings are derived here; ten-wicket-match is the per-match wicket total. **Overs** are stored for
    this match using the match's own balls-per-over (Law 17, from playing conditions — six, eight or any
    historically configured value), so career economy sums true overs across mixed-over-length eras and
    never assumes one over length. ``overs_known`` is 0 when the over length is unrecorded (that match is
    then excluded from the career economy and the figure is flagged)."""
    bpo = (matches.effective_conditions(conn, match["id"]).get("conditions") or {}).get("balls_per_over")
    rows = conn.execute(
        text(
            "SELECT be.person_id AS pid, coalesce(be.legal_balls,0) AS balls, be.legal_balls AS balls_raw, "
            " coalesce(be.maidens,0) AS maidens, coalesce(be.runs_conceded,0) AS runs, "
            " be.runs_conceded AS runs_raw, coalesce(be.wickets,0) AS wickets, be.wickets AS wickets_raw, "
            " i.bowling_team_id AS team_id "
            "FROM bowling_entry be JOIN innings i ON i.id = be.innings_id "
            "WHERE i.match_id = :m AND be.person_id IS NOT NULL"
        ),
        {"m": match["id"]},
    ).mappings().all()
    home, _ = _home_away(conn, match["id"])
    gf = _is_grand_final(match)
    cls = match.get("classification")
    agg: dict[Any, dict[str, Any]] = {}
    for r in rows:
        a = agg.setdefault(r["pid"], {"team_id": r["team_id"], "innings": 0, "balls": 0, "balls_known": 0,
                                      "maidens": 0, "runs": 0, "wickets": 0, "wickets_known": 0,
                                      "five_wkt_innings": 0, "bbi_w": -1, "bbi_r": None})
        a["innings"] += 1
        a["balls"] += r["balls"]
        if r["balls_raw"] is not None:
            a["balls_known"] += 1
        a["maidens"] += r["maidens"]
        a["runs"] += r["runs"]
        a["wickets"] += r["wickets"]
        if r["wickets_raw"] is not None:
            a["wickets_known"] += 1
        if r["wickets"] >= 5:
            a["five_wkt_innings"] += 1
        # best bowling in an innings: most wickets, then fewest runs
        if r["wickets"] > a["bbi_w"] or (r["wickets"] == a["bbi_w"] and a["bbi_r"] is not None
                                         and r["runs"] < a["bbi_r"]):
            a["bbi_w"], a["bbi_r"] = r["wickets"], r["runs"]
    out = []
    for pid, a in agg.items():
        # overs for THIS match from its own balls-per-over (never a single assumed over length)
        overs = round(a["balls"] / bpo, 4) if (bpo and a["balls"]) else 0
        out.append({"subject_kind": "person", "subject_id": pid, "team_id": a["team_id"], **_match_scope(match),
                    "metrics": {"innings": a["innings"], "balls": a["balls"], "balls_known": a["balls_known"],
                                "overs": overs, "overs_known": 1 if bpo else 0,
                                "maidens": a["maidens"], "runs": a["runs"], "wickets": a["wickets"],
                                "wickets_known": a["wickets_known"], "five_wkt_innings": a["five_wkt_innings"],
                                "bbi_wickets": max(a["bbi_w"], 0), "bbi_runs": a["bbi_r"],
                                "ten_wkt_match": 1 if a["wickets"] >= 10 else 0, "match_wickets": a["wickets"],
                                "is_home": str(a["team_id"]) == str(home) if home else None,
                                "classification": cls, "grand_final": gf}})
    return out


def _calc_player_fielding(conn: Connection, match: dict[str, Any]) -> list[dict[str, Any]]:
    """Fielding/wicketkeeping credits per person from dismissal fielder attribution. A wicketkeeper
    catch (caught_behind, or a catch where the fielder is the side's keeper) and a stumping are kept
    as distinct wicketkeeping classifications; run outs are counted separately and never as bowler
    wickets. Unknown fielders are not credited."""
    keepers = _keepers_by_team(conn, match["id"])
    rows = conn.execute(
        # A caught-and-bowled is a catch taken by the BOWLER, so credit the bowler when no separate fielder
        # is named (the scorecard's Fielder is blank for c&b). Every other dismissal credits the fielder.
        text("SELECT CASE WHEN be.dismissal_type = 'caught_and_bowled' "
             "            THEN coalesce(be.fielder_person_id, be.bowler_person_id) "
             "            ELSE be.fielder_person_id END AS pid, "
             "       be.dismissal_type AS dt, i.bowling_team_id AS team_id "
             "FROM batting_entry be JOIN innings i ON i.id = be.innings_id "
             "WHERE i.match_id = :m "
             "AND be.dismissal_type IN ('caught','caught_and_bowled','caught_behind','stumped','run_out') "
             "AND (be.fielder_person_id IS NOT NULL "
             "     OR (be.dismissal_type = 'caught_and_bowled' AND be.bowler_person_id IS NOT NULL))"),
        {"m": match["id"]},
    ).mappings().all()
    home, _ = _home_away(conn, match["id"])
    cls = match.get("classification")
    gf = _is_grand_final(match)
    agg: dict[Any, dict[str, Any]] = {}

    def _a(pid: Any, team: Any) -> dict[str, Any]:
        return agg.setdefault(pid, {"team_id": team, "field_catches": 0, "keeper_catches": 0,
                                    "stumpings": 0, "run_outs": 0, "run_out_assists": 0})

    for r in rows:
        pid, dt, team = r["pid"], r["dt"], r["team_id"]
        a = _a(pid, team)
        is_keeper = str(pid) in keepers.get(str(team), set())
        if dt == "stumped":
            a["stumpings"] += 1
        elif dt == "caught_behind" or (dt == "caught" and is_keeper):
            a["keeper_catches"] += 1
        elif dt in ("caught", "caught_and_bowled"):
            a["field_catches"] += 1
        elif dt == "run_out":
            a["run_outs"] += 1
    # additional run-out fielders (R-3): each is credited a run-out ASSIST — distinct from the primary
    # fielder's run_out, so existing run_outs figures never change and the wicket is never double counted.
    assists = conn.execute(
        text("SELECT df.person_id AS pid, i.bowling_team_id AS team_id "
             "FROM dismissal_fielder df JOIN batting_entry be ON be.id = df.batting_entry_id "
             "JOIN innings i ON i.id = be.innings_id "
             "WHERE i.match_id = :m AND be.dismissal_type = 'run_out'"),
        {"m": match["id"]},
    ).mappings().all()
    for r in assists:
        _a(r["pid"], r["team_id"])["run_out_assists"] += 1
    out = []
    for pid, a in agg.items():
        out.append({"subject_kind": "person", "subject_id": pid, "team_id": a["team_id"], **_match_scope(match),
                    "metrics": {"field_catches": a["field_catches"], "keeper_catches": a["keeper_catches"],
                                "stumpings": a["stumpings"], "run_outs": a["run_outs"],
                                "run_out_assists": a["run_out_assists"],
                                # total catches include keeper catches; keeper dismissals kept separate
                                "catches": a["field_catches"] + a["keeper_catches"],
                                "keeper_dismissals": a["keeper_catches"] + a["stumpings"],
                                "is_home": str(a["team_id"]) == str(home) if home else None,
                                "classification": cls, "grand_final": gf}})
    return out


def _calc_player_captaincy(conn: Connection, match: dict[str, Any]) -> list[dict[str, Any]]:
    """One contribution per credited captain (acting captain if recorded, else captain). Never
    double-credits a match to two captains for one side; unknown captains are excluded. A forfeit with no
    play creates NO captaincy appearance (approved forfeit policy)."""
    if _forfeit_no_play(conn, match):
        return []
    home, _ = _home_away(conn, match["id"])
    cls = match.get("classification")
    gf = _is_grand_final(match)
    rows = conn.execute(
        text("SELECT team_id, captain_person_id, acting_captain_person_id FROM match_team WHERE match_id = :m"),
        {"m": match["id"]},
    ).mappings().all()
    out = []
    for r in rows:
        cap = r["acting_captain_person_id"] or r["captain_person_id"]
        if cap is None:
            continue  # unknown captain — excluded, never attributed
        res = _team_result(match, r["team_id"], home)
        out.append({"subject_kind": "person", "subject_id": cap, "team_id": r["team_id"], **_match_scope(match),
                    "metrics": {"captained": 1, "win": int(res == "win"), "loss": int(res == "loss"),
                                "draw": int(res == "draw"), "tie": int(res == "tie"),
                                "no_result": int(res == "no_result"), "unknown_result": int(res == "unknown"),
                                "gf_captained": int(gf), "gf_win": int(gf and res == "win"),
                                "is_home": str(r["team_id"]) == str(home) if home else None,
                                "classification": cls, "grand_final": gf, "result": res}})
    return out


def _calc_team_result(conn: Connection, match: dict[str, Any]) -> list[dict[str, Any]]:
    """One contribution per team in the match (subject = team): played + result, for team records and
    streaks. Uses the match date for chronological ordering downstream."""
    home, _ = _home_away(conn, match["id"])
    cls = match.get("classification")
    gf = _is_grand_final(match)
    rows = conn.execute(text("SELECT team_id FROM match_team WHERE match_id = :m"), {"m": match["id"]}).mappings().all()
    out = []
    for r in rows:
        res = _team_result(match, r["team_id"], home)
        out.append({"subject_kind": "team", "subject_id": r["team_id"], "team_id": r["team_id"], **_match_scope(match),
                    "metrics": {"played": 1, "win": int(res == "win"), "loss": int(res == "loss"),
                                "draw": int(res == "draw"), "tie": int(res == "tie"),
                                "no_result": int(res == "no_result"), "unknown_result": int(res == "unknown"),
                                "is_home": str(r["team_id"]) == str(home) if home else None,
                                "classification": cls, "grand_final": gf, "result": res}})
    return out


def _calc_player_appearance(conn: Connection, match: dict[str, Any]) -> list[dict[str, Any]]:
    """One appearance per person who was on the scoresheet for the match — anyone listed in the batting
    card (including "did not bat"), the bowling card, as a fielder on a dismissal, or as a recorded
    captain/keeper (no separate team-sheet table). A player listed as "did not bat" was in the XI and
    counts as a match played, even though it is not a batting innings; only a genuine "absent" (took no
    part) is excluded. Each person once. A forfeit with no play creates NO player appearances (approved
    forfeit policy); the team still gets its result via ``_calc_team_result``."""
    if _forfeit_no_play(conn, match):
        return []
    home, _ = _home_away(conn, match["id"])
    cls = match.get("classification")
    gf = _is_grand_final(match)
    # Exactly ONE appearance per person. A person can be tied to more than one team in a match (e.g.
    # an intra-club fixture whose two sides are the same club, or a scorer anomaly); pick a single team
    # by priority (batted/listed > bowled > fielded > captain > keeper) so the per-person appearance is unique.
    rows = conn.execute(
        text(
            "SELECT DISTINCT ON (pid) pid, team_id FROM ("
            # anyone on the batting card counts as having played — including "did not bat"; exclude only a
            # genuine "absent" (named but took no part in the match)
            " SELECT be.person_id AS pid, i.batting_team_id AS team_id, 1 AS pri FROM batting_entry be "
            "   JOIN innings i ON i.id = be.innings_id WHERE i.match_id = :m AND be.person_id IS NOT NULL "
            "     AND (be.dismissal_type IS NULL OR be.dismissal_type <> 'absent')"
            " UNION ALL SELECT bo.person_id, i.bowling_team_id, 2 FROM bowling_entry bo "
            "   JOIN innings i ON i.id = bo.innings_id WHERE i.match_id = :m AND bo.person_id IS NOT NULL "
            " UNION ALL SELECT be.fielder_person_id, i.bowling_team_id, 3 FROM batting_entry be "
            "   JOIN innings i ON i.id = be.innings_id WHERE i.match_id = :m AND be.fielder_person_id IS NOT NULL "
            " UNION ALL SELECT mt.captain_person_id, mt.team_id, 4 FROM match_team mt WHERE mt.match_id = :m AND mt.captain_person_id IS NOT NULL "
            " UNION ALL SELECT mt.wicketkeeper_person_id, mt.team_id, 5 FROM match_team mt WHERE mt.match_id = :m AND mt.wicketkeeper_person_id IS NOT NULL "
            ") s WHERE pid IS NOT NULL ORDER BY pid, pri"
        ),
        {"m": match["id"]},
    ).mappings().all()
    res_by_team: dict[str, str] = {}
    out = []
    for r in rows:
        team = r["team_id"]
        key = str(team)
        if key not in res_by_team:
            res_by_team[key] = _team_result(match, team, home)
        res = res_by_team[key]
        out.append({"subject_kind": "person", "subject_id": r["pid"], "team_id": team, **_match_scope(match),
                    "metrics": {"matches": 1, "win": int(res == "win"), "loss": int(res == "loss"),
                                "is_home": str(team) == str(home) if home else None,
                                "classification": cls, "grand_final": gf, "result": res}})
    return out


# registry — statistical modules append their calculators here (the integration point)
CALCULATORS: dict[str, Callable[[Connection, dict[str, Any]], list[dict[str, Any]]]] = {
    "player_batting": _calc_player_batting,
    "player_bowling": _calc_player_bowling,
    "player_fielding": _calc_player_fielding,
    "player_captaincy": _calc_player_captaincy,
    "player_appearance": _calc_player_appearance,
    "team_result": _calc_team_result,
}


def recompute_match(conn: Connection, workspace_id: UUID, actor: str, match_id: UUID) -> dict[str, Any]:
    """Recompute a single match's official contributions. Idempotent: existing rows for the match are
    removed first, then, only if the match is an approved statistics-eligible scorecard, fresh rows
    are written. A non-official match ends with no contributions. Never double counts."""
    match = matches.get_match(conn, match_id)
    if match is None:
        raise ValueError("match_not_found")
    conn.execute(text("DELETE FROM match_stat_contribution WHERE match_id = :m"), {"m": match_id})
    written = 0
    if matches.official_for_stats(match):
        for name, fn in CALCULATORS.items():
            for c in fn(conn, match):
                conn.execute(
                    text("INSERT INTO match_stat_contribution"
                         "(workspace_id, match_id, calculator, subject_kind, subject_id, team_id, "
                         " season_id, grade_id, competition_id, metrics) "
                         "VALUES (:w, :m, :cal, :sk, :sid, :tid, :se, :gr, :co, CAST(:met AS jsonb))"),
                    {"w": workspace_id, "m": match_id, "cal": name, "sk": c["subject_kind"],
                     "sid": c["subject_id"], "tid": c.get("team_id"), "se": c.get("season_id"),
                     "gr": c.get("grade_id"), "co": c.get("competition_id"),
                     "met": json.dumps(c["metrics"])},
                )
                written += 1
    # Phase 15: an approved-stat change makes published reports/profiles stale — flag them so the
    # publishing edge refreshes the public snapshot (public serving keeps the last snapshot meanwhile).
    conn.execute(text("UPDATE publication SET stale = true WHERE workspace_id = :w AND status = 'published'"),
                 {"w": workspace_id})
    audit.write_audit(conn, workspace_id, actor, "stats.recompute_match", entity="match",
                      entity_id=str(match_id), after={"contributions": written, "official": matches.official_for_stats(match)})
    return {"match_id": str(match_id), "contributions": written, "official": matches.official_for_stats(match)}


def backfill(conn: Connection, workspace_id: UUID, actor: str) -> dict[str, Any]:
    """Recompute the ledger for every match in the workspace (historical backfill). Idempotent."""
    ids = [r[0] for r in conn.execute(text("SELECT id FROM match"))]
    total = 0
    for mid in ids:
        total += recompute_match(conn, workspace_id, actor, mid)["contributions"]
    audit.write_audit(conn, workspace_id, actor, "stats.backfill", entity="workspace",
                      entity_id=str(workspace_id), after={"matches": len(ids), "contributions": total})
    return {"matches": len(ids), "contributions": total}


def official_player_batting(conn: Connection, workspace_id: UUID, person_id: UUID) -> dict[str, Any]:
    """Official career batting for a person — delegates to the ONE statistics engine (merge-aware,
    unknown-aware). Kept as the Phase 7 entry point; it is a thin wrapper so there is a single
    authoritative calculation, never a competing formula. ``not_out`` is retained as a back-compat
    alias of the engine's ``not_outs``."""
    from onestats.domain.stats import engine
    d = engine.person_batting(conn, {"workspace_id": workspace_id}, person_id)
    d["not_out"] = d.get("not_outs", 0)
    return d


def official_player_bowling(conn: Connection, workspace_id: UUID, person_id: UUID,
                            *, over_length: int = 6) -> dict[str, Any]:
    """Official career bowling for a person — delegates to the ONE statistics engine (merge-aware).
    Economy uses the given over length via the engine (never a hardcoded six-ball over); the career
    default is six balls, configurable for historical eight-ball-over eras."""
    from onestats.domain.stats import engine
    return engine.person_bowling(conn, {"workspace_id": workspace_id}, person_id, over_length=over_length)
