"""Innings & extras (Phase 6, Stage 2).

An innings of a match, with batting/bowling sides, status, the five extras and the CricketStatz
``iresult`` preserved raw (mapping unresolved — not guessed). Totals are distinct concepts:

* **source** — the five extras here; batting runs (Stage 3) and bowling-conceded runs (Stage 4)
  are summed by the shared derivation once those stages exist;
* **derived** — Σ batting runs + extras (and wickets = genuine dismissals); until the batting
  stage exists the batting component is **unknown**, so the derived total stays unknown, never 0;
* **official override** — an optional reviewer-set total/wickets with reason, evidence, approver
  and timestamp, stored separately and never overwriting the source scorecard.

Validation is **non-blocking**: inconsistencies are returned as warnings so legitimate incomplete
historical innings still save. Unknown stays unknown. Workspace-scoped (RLS); ``match.manage``;
audited.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain import audit

STATUSES = ("in_progress", "completed", "declared", "closed", "forfeited", "incomplete", "unknown")
_EXTRAS = ("byes", "legbyes", "wides", "noballs", "penalty")
_COLS = (
    "id, workspace_id, match_id, inns_number, batting_team_id, bowling_team_id, status, "
    "byes, legbyes, wides, noballs, penalty, official_total, official_wickets, override_reason, "
    "override_evidence, override_by, override_at, iresult_raw, iresult, iresult_status, notes, "
    "source_system, source_ref, created_at, updated_at"
)


def _batting_table_exists(conn: Connection) -> bool:
    return conn.execute(text("SELECT to_regclass('public.batting_entry')")).scalar_one() is not None


def get_innings(conn: Connection, innings_id: UUID) -> dict[str, Any] | None:
    r = conn.execute(text(f"SELECT {_COLS} FROM innings WHERE id = :id"), {"id": innings_id}).mappings().first()
    return dict(r) if r else None


def list_innings(conn: Connection, match_id: UUID) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(f"SELECT {_COLS} FROM innings WHERE match_id = :m ORDER BY inns_number"), {"m": match_id}
    ).mappings().all()
    return [dict(r) for r in rows]


def _is_match_side(conn: Connection, match_id: UUID, team_id: UUID) -> bool:
    return conn.execute(
        text("SELECT 1 FROM match_team WHERE match_id = :m AND team_id = :t"), {"m": match_id, "t": team_id}
    ).first() is not None


def create_innings(
    conn: Connection, workspace_id: UUID, actor: str, *, match_id: UUID, inns_number: int,
    batting_team_id: UUID | None = None, bowling_team_id: UUID | None = None, status: str = "unknown",
    byes: int | None = None, legbyes: int | None = None, wides: int | None = None,
    noballs: int | None = None, penalty: int | None = None, iresult_raw: str | None = None,
    notes: str | None = None, source_system: str | None = None, source_ref: str | None = None,
) -> UUID:
    if conn.execute(text("SELECT 1 FROM match WHERE id = :m"), {"m": match_id}).first() is None:
        raise ValueError("match_not_found")
    if inns_number < 1:
        raise ValueError("invalid_inns_number")
    if status not in STATUSES:
        raise ValueError("invalid_status")
    if batting_team_id is not None and bowling_team_id is not None and batting_team_id == bowling_team_id:
        raise ValueError("teams_must_differ")
    for tid in (batting_team_id, bowling_team_id):
        if tid is not None and not _is_match_side(conn, match_id, tid):
            raise ValueError("team_not_in_match")
    innings_id = conn.execute(
        text(
            "INSERT INTO innings(workspace_id, match_id, inns_number, batting_team_id, bowling_team_id, "
            " status, byes, legbyes, wides, noballs, penalty, iresult_raw, notes, source_system, source_ref) "
            "VALUES (:w, :m, :n, :bt, :bw, :st, :b, :lb, :wd, :nb, :pen, :ir, :notes, :ss, :sr) RETURNING id"
        ),
        {"w": workspace_id, "m": match_id, "n": inns_number, "bt": batting_team_id, "bw": bowling_team_id,
         "st": status, "b": byes, "lb": legbyes, "wd": wides, "nb": noballs, "pen": penalty,
         "ir": iresult_raw, "notes": notes, "ss": source_system, "sr": source_ref},
    ).scalar_one()
    audit.write_audit(conn, workspace_id, actor, "innings.create", entity="innings", entity_id=str(innings_id),
                      after={"match_id": str(match_id), "inns_number": inns_number, "status": status})
    return innings_id


def update_innings(conn: Connection, workspace_id: UUID, actor: str, innings_id: UUID, **fields: Any) -> dict[str, Any]:
    before = get_innings(conn, innings_id)
    if before is None:
        raise ValueError("innings_not_found")
    if "status" in fields and fields["status"] is not None and fields["status"] not in STATUSES:
        raise ValueError("invalid_status")
    allowed = {"status", "batting_team_id", "bowling_team_id", "byes", "legbyes", "wides",
               "noballs", "penalty", "iresult_raw", "notes"}
    data = {k: v for k, v in fields.items() if k in allowed and v is not None}
    for key in ("batting_team_id", "bowling_team_id"):
        if key in data and not _is_match_side(conn, before["match_id"], data[key]):
            raise ValueError("team_not_in_match")
    if data:
        sets = ", ".join(f"{k} = :{k}" for k in data)
        conn.execute(text(f"UPDATE innings SET {sets}, updated_at = now() WHERE id = :id"), {**data, "id": innings_id})
    after = get_innings(conn, innings_id)
    audit.write_audit(conn, workspace_id, actor, "innings.update", entity="innings", entity_id=str(innings_id),
                      before=before, after=after)
    return after


def set_official_total(
    conn: Connection, workspace_id: UUID, actor: str, innings_id: UUID, *, total: int | None,
    wickets: int | None = None, reason: str | None = None, evidence: str | None = None,
) -> dict[str, Any]:
    """Record an official innings total/wickets override (e.g. a known scorebook total that the
    partial card cannot reproduce). Source extras/scorecard are never changed."""
    before = get_innings(conn, innings_id)
    if before is None:
        raise ValueError("innings_not_found")
    if total is not None and total < 0:
        raise ValueError("invalid_total")
    if wickets is not None and not (0 <= wickets <= 10):
        raise ValueError("invalid_wickets")
    conn.execute(
        text("UPDATE innings SET official_total = :t, official_wickets = :w, override_reason = :r, "
             "override_evidence = :ev, override_by = :by, override_at = now(), updated_at = now() WHERE id = :id"),
        {"t": total, "w": wickets, "r": reason, "ev": evidence, "by": actor, "id": innings_id},
    )
    after = get_innings(conn, innings_id)
    audit.write_audit(conn, workspace_id, actor, "innings.official_override", entity="innings",
                      entity_id=str(innings_id), before=before, after=after)
    return after


def _sum_known(values: list[Any]) -> int | None:
    known = [v for v in values if v is not None]
    return sum(known) if known else None


def totals(conn: Connection, innings_id: UUID) -> dict[str, Any]:
    """Distinct total components. ``extras_total`` is the sum of the recorded extras (unknown if
    none recorded). ``batting_runs``/``bowling_conceded`` derive from later scorecard stages and
    are unknown until then; ``derived_total`` = batting_runs + extras_total (unknown if batting
    unknown). ``official_total`` is the override if set. Unknowns never become zero."""
    inn = get_innings(conn, innings_id)
    if inn is None:
        raise ValueError("innings_not_found")
    extras_total = _sum_known([inn[e] for e in _EXTRAS])
    batting_runs: int | None = None
    bowling_conceded: int | None = None
    derived_wickets: int | None = None
    if _batting_table_exists(conn):  # Stage 3+ — compute from the batting card
        batting_runs = conn.execute(
            text("SELECT sum(runs) FROM batting_entry WHERE innings_id = :i AND runs IS NOT NULL"),
            {"i": innings_id},
        ).scalar_one_or_none()
        # genuine dismissals only — no-innings (dnb/absent), not-out and unresolved statuses are
        # not wickets; unknown_out (batter was out, manner unknown) counts. Mirrors
        # batting.NON_WICKET_STATUSES.
        derived_wickets = conn.execute(
            text("SELECT count(*) FROM batting_entry WHERE innings_id = :i AND dismissal_type IS NOT NULL "
                 "AND dismissal_type NOT IN ('dnb','absent','not_out','retired_not_out','retired','unknown')"),
            {"i": innings_id},
        ).scalar_one()
    if conn.execute(text("SELECT to_regclass('public.bowling_entry')")).scalar_one() is not None:
        bowling_conceded = conn.execute(
            text("SELECT sum(runs_conceded) FROM bowling_entry WHERE innings_id = :i AND runs_conceded IS NOT NULL"),
            {"i": innings_id},
        ).scalar_one_or_none()
    derived_total = None
    if batting_runs is not None or extras_total is not None:
        derived_total = (batting_runs or 0) + (extras_total or 0) if (batting_runs is not None) else None
    return {
        "innings_id": str(innings_id),
        "extras_total": extras_total,
        "batting_runs": batting_runs,
        "bowling_conceded": bowling_conceded,
        "derived_total": derived_total,
        "derived_wickets": derived_wickets,
        "official_total": inn["official_total"],
        "official_wickets": inn["official_wickets"],
    }


def validation_warnings(conn: Connection, innings_id: UUID) -> list[str]:
    """Non-blocking consistency checks — a legitimate incomplete historical innings still saves."""
    inn = get_innings(conn, innings_id)
    if inn is None:
        raise ValueError("innings_not_found")
    warnings: list[str] = []
    extras_total = _sum_known([inn[e] for e in _EXTRAS])
    if inn["official_total"] is not None and extras_total is not None and inn["official_total"] < extras_total:
        warnings.append("official_total_less_than_extras")
    if inn["official_wickets"] is not None and inn["official_wickets"] > 10:
        warnings.append("official_wickets_gt_10")
    t = totals(conn, innings_id)
    if (t["derived_total"] is not None and inn["official_total"] is not None
            and t["derived_total"] != inn["official_total"]):
        warnings.append("derived_total_differs_from_official")  # informational; both are kept
    if inn["batting_team_id"] is None or inn["bowling_team_id"] is None:
        warnings.append("innings_teams_unknown")
    return warnings
