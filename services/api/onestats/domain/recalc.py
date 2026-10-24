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


def _calc_player_batting(conn: Connection, match: dict[str, Any]) -> list[dict[str, Any]]:
    """One batting contribution per person in the match (aggregated across that match's innings)."""
    rows = conn.execute(
        text(
            "SELECT be.person_id, "
            " count(*) FILTER (WHERE be.dismissal_type IS NULL OR be.dismissal_type NOT IN ('dnb','absent')) AS innings, "
            " coalesce(sum(be.runs), 0) AS runs, coalesce(sum(be.balls_faced), 0) AS balls, "
            " coalesce(sum(be.fours), 0) AS fours, coalesce(sum(be.sixes), 0) AS sixes, "
            f" count(*) FILTER (WHERE be.dismissal_type IS NOT NULL AND be.dismissal_type NOT IN ({_NON_WICKET})) AS dismissed, "
            " count(*) FILTER (WHERE be.dismissal_type IN ('not_out','retired_not_out')) AS not_out, "
            " min(i.batting_team_id::text) AS team_id "
            "FROM batting_entry be JOIN innings i ON i.id = be.innings_id "
            "WHERE i.match_id = :m AND be.person_id IS NOT NULL "
            "GROUP BY be.person_id"
        ),
        {"m": match["id"]},
    ).mappings().all()
    out = []
    for r in rows:
        if r["innings"] == 0:  # the person only has did-not-bat rows — not a batting innings
            continue
        out.append({"subject_kind": "person", "subject_id": r["person_id"],
                    "team_id": r["team_id"], **_match_scope(match),
                    "metrics": {"innings": r["innings"], "runs": r["runs"], "balls": r["balls"],
                                "fours": r["fours"], "sixes": r["sixes"],
                                "dismissed": r["dismissed"], "not_out": r["not_out"]}})
    return out


def _calc_player_bowling(conn: Connection, match: dict[str, Any]) -> list[dict[str, Any]]:
    """One bowling contribution per person in the match (aggregated across that match's innings)."""
    rows = conn.execute(
        text(
            "SELECT be.person_id, count(*) AS innings, coalesce(sum(be.legal_balls), 0) AS balls, "
            " coalesce(sum(be.maidens), 0) AS maidens, coalesce(sum(be.runs_conceded), 0) AS runs, "
            " coalesce(sum(be.wickets), 0) AS wickets, min(i.bowling_team_id::text) AS team_id "
            "FROM bowling_entry be JOIN innings i ON i.id = be.innings_id "
            "WHERE i.match_id = :m AND be.person_id IS NOT NULL "
            "GROUP BY be.person_id"
        ),
        {"m": match["id"]},
    ).mappings().all()
    return [{"subject_kind": "person", "subject_id": r["person_id"], "team_id": r["team_id"],
             **_match_scope(match),
             "metrics": {"innings": r["innings"], "balls": r["balls"], "maidens": r["maidens"],
                         "runs": r["runs"], "wickets": r["wickets"]}} for r in rows]


# registry — future statistical modules append their calculators here (the integration point)
CALCULATORS: dict[str, Callable[[Connection, dict[str, Any]], list[dict[str, Any]]]] = {
    "player_batting": _calc_player_batting,
    "player_bowling": _calc_player_bowling,
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


def _merge_aware(column: str = "subject_id") -> str:
    # match the subject directly, or any identity merged into it (so a corrected identity combines)
    return f"({column} = :p OR {column} IN (SELECT id FROM person WHERE merged_into_id = :p))"


def official_player_batting(conn: Connection, workspace_id: UUID, person_id: UUID) -> dict[str, Any]:
    """Official career batting for a person from the approved ledger (merge-aware). Unknown stays 0
    only where genuinely nothing is recorded; averages are None when undefined."""
    r = conn.execute(
        text(
            "SELECT count(DISTINCT match_id) AS matches, "
            " coalesce(sum((metrics->>'innings')::int), 0) AS innings, "
            " coalesce(sum((metrics->>'runs')::int), 0) AS runs, "
            " coalesce(sum((metrics->>'balls')::int), 0) AS balls, "
            " coalesce(sum((metrics->>'fours')::int), 0) AS fours, "
            " coalesce(sum((metrics->>'sixes')::int), 0) AS sixes, "
            " coalesce(sum((metrics->>'dismissed')::int), 0) AS dismissed, "
            " coalesce(sum((metrics->>'not_out')::int), 0) AS not_out "
            f"FROM match_stat_contribution WHERE calculator = 'player_batting' AND {_merge_aware()}"
        ),
        {"p": person_id},
    ).mappings().one()
    d = dict(r)
    d["average"] = round(d["runs"] / d["dismissed"], 2) if d["dismissed"] else None
    d["strike_rate"] = round(d["runs"] * 100 / d["balls"], 2) if d["balls"] else None
    return d


def official_player_bowling(conn: Connection, workspace_id: UUID, person_id: UUID) -> dict[str, Any]:
    """Official career bowling for a person from the approved ledger (merge-aware)."""
    r = conn.execute(
        text(
            "SELECT count(DISTINCT match_id) AS matches, "
            " coalesce(sum((metrics->>'innings')::int), 0) AS innings, "
            " coalesce(sum((metrics->>'balls')::int), 0) AS balls, "
            " coalesce(sum((metrics->>'maidens')::int), 0) AS maidens, "
            " coalesce(sum((metrics->>'runs')::int), 0) AS runs, "
            " coalesce(sum((metrics->>'wickets')::int), 0) AS wickets "
            f"FROM match_stat_contribution WHERE calculator = 'player_bowling' AND {_merge_aware()}"
        ),
        {"p": person_id},
    ).mappings().one()
    d = dict(r)
    d["average"] = round(d["runs"] / d["wickets"], 2) if d["wickets"] else None
    d["economy"] = round(d["runs"] * 6 / d["balls"], 2) if d["balls"] else None
    return d
