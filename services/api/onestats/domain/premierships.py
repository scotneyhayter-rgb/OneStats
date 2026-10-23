"""Premierships (Phase 6, Stage 6).

A premiership is the competition/grade/season outcome — the premiership-winning team(s), an
optional runner-up, the deciding series and/or match where applicable, a verification status and
source evidence. It sits on top of the finals-series structure (``finals_series``, deliverable
0011) and the match classification model, but is a **separate, explicit record**:

* A premiership is **never** created automatically because a team won a Grand Final match. Winning
  a match classified as a Grand Final does not, by itself, award a premiership — the caller records
  the premiership explicitly, with evidence or a verified result.
* Classifications are **never** inferred from round labels, team names or incomplete sources
  (deliverable 14); this module reads none of those to decide a winner.
* **Shared premierships** are first-class: two or more winning teams on one premiership record.
* **Abandoned / not-awarded / unknown** outcomes are representable; unknown stays unknown.

Corrections are audited. Consistency issues are returned as **non-blocking warnings**. All
operations are workspace-scoped (RLS) and governed by ``competition.manage``.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain import audit

OUTCOMES = ("awarded", "shared", "abandoned", "not_awarded", "unknown")
VERIFICATION_STATUSES = ("unverified", "provisional", "verified", "disputed")
WINNER_ROLES = ("winner", "shared_winner")

_COLS = (
    "id, workspace_id, competition_id, season_id, grade_id, outcome, runner_up_team_id, "
    "deciding_series_id, deciding_match_id, verification_status, evidence, notes, source_system, "
    "source_ref, created_at, updated_at"
)
_SET_FIELDS = ("season_id", "grade_id", "outcome", "runner_up_team_id", "deciding_series_id",
               "deciding_match_id", "verification_status", "evidence", "notes")


def _exists(conn: Connection, table: str, entity_id: UUID) -> bool:
    return conn.execute(text(f"SELECT 1 FROM {table} WHERE id = :x"), {"x": entity_id}).first() is not None


def get_premiership(conn: Connection, premiership_id: UUID) -> dict[str, Any] | None:
    r = conn.execute(text(f"SELECT {_COLS} FROM premiership WHERE id = :id"),
                     {"id": premiership_id}).mappings().first()
    return dict(r) if r else None


def list_premierships(conn: Connection, *, competition_id: UUID | None = None) -> list[dict[str, Any]]:
    sql = f"SELECT {_COLS} FROM premiership"
    params: dict[str, Any] = {}
    if competition_id is not None:
        sql += " WHERE competition_id = :c"
        params["c"] = competition_id
    sql += " ORDER BY created_at"
    return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]


def list_winners(conn: Connection, premiership_id: UUID) -> list[dict[str, Any]]:
    rows = conn.execute(
        text("SELECT id, team_id, role FROM premiership_team WHERE premiership_id = :p ORDER BY created_at"),
        {"p": premiership_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def create_premiership(
    conn: Connection, workspace_id: UUID, actor: str, *, competition_id: UUID,
    season_id: UUID | None = None, grade_id: UUID | None = None, outcome: str = "unknown",
    runner_up_team_id: UUID | None = None, deciding_series_id: UUID | None = None,
    deciding_match_id: UUID | None = None, verification_status: str = "unverified",
    evidence: str | None = None, notes: str | None = None, source_system: str | None = None,
    source_ref: str | None = None,
) -> UUID:
    if outcome not in OUTCOMES:
        raise ValueError("invalid_outcome")
    if verification_status not in VERIFICATION_STATUSES:
        raise ValueError("invalid_verification_status")
    if not _exists(conn, "competition", competition_id):
        raise ValueError("competition_not_found")
    for table, val, err in (
        ("season", season_id, "season_not_found"),
        ("grade", grade_id, "grade_not_found"),
        ("finals_series", deciding_series_id, "series_not_found"),
        ("match", deciding_match_id, "match_not_found"),
    ):
        if val is not None and not _exists(conn, table, val):
            raise ValueError(err)
    premiership_id = conn.execute(
        text(
            "INSERT INTO premiership(workspace_id, competition_id, season_id, grade_id, outcome, "
            " runner_up_team_id, deciding_series_id, deciding_match_id, verification_status, "
            " evidence, notes, source_system, source_ref) "
            "VALUES (:w, :c, :s, :g, :o, :ru, :ds, :dm, :vs, :ev, :n, :ss, :sr) RETURNING id"
        ),
        {"w": workspace_id, "c": competition_id, "s": season_id, "g": grade_id, "o": outcome,
         "ru": runner_up_team_id, "ds": deciding_series_id, "dm": deciding_match_id,
         "vs": verification_status, "ev": evidence, "n": notes, "ss": source_system, "sr": source_ref},
    ).scalar_one()
    audit.write_audit(conn, workspace_id, actor, "premiership.create", entity="premiership",
                      entity_id=str(premiership_id),
                      after={"competition_id": str(competition_id), "outcome": outcome,
                             "verification_status": verification_status})
    return premiership_id


def add_winner(
    conn: Connection, workspace_id: UUID, actor: str, premiership_id: UUID, team_id: UUID,
    *, role: str = "winner",
) -> dict[str, Any]:
    """Record a premiership-winning team. Explicit only — never derived from a match result.
    Idempotent on (premiership, team)."""
    if get_premiership(conn, premiership_id) is None:
        raise ValueError("premiership_not_found")
    if role not in WINNER_ROLES:
        raise ValueError("invalid_role")
    if not _exists(conn, "team", team_id):
        raise ValueError("team_not_found")
    existing = conn.execute(
        text("SELECT id FROM premiership_team WHERE premiership_id = :p AND team_id = :t"),
        {"p": premiership_id, "t": team_id},
    ).scalar_one_or_none()
    if existing is not None:
        return {"premiership_team_id": existing, "created": False}
    pt_id = conn.execute(
        text("INSERT INTO premiership_team(workspace_id, premiership_id, team_id, role) "
             "VALUES (:w, :p, :t, :r) RETURNING id"),
        {"w": workspace_id, "p": premiership_id, "t": team_id, "r": role},
    ).scalar_one()
    audit.write_audit(conn, workspace_id, actor, "premiership.add_winner", entity="premiership",
                      entity_id=str(premiership_id), after={"team_id": str(team_id), "role": role})
    return {"premiership_team_id": pt_id, "created": True}


def remove_winner(conn: Connection, workspace_id: UUID, actor: str, premiership_id: UUID, team_id: UUID) -> None:
    if get_premiership(conn, premiership_id) is None:
        raise ValueError("premiership_not_found")
    conn.execute(
        text("DELETE FROM premiership_team WHERE premiership_id = :p AND team_id = :t"),
        {"p": premiership_id, "t": team_id},
    )
    audit.write_audit(conn, workspace_id, actor, "premiership.remove_winner", entity="premiership",
                      entity_id=str(premiership_id), after={"team_id": str(team_id)})


def update_premiership(conn: Connection, workspace_id: UUID, actor: str, premiership_id: UUID, **fields: Any) -> dict[str, Any]:
    before = get_premiership(conn, premiership_id)
    if before is None:
        raise ValueError("premiership_not_found")
    if fields.get("outcome") is not None and fields["outcome"] not in OUTCOMES:
        raise ValueError("invalid_outcome")
    if fields.get("verification_status") is not None and fields["verification_status"] not in VERIFICATION_STATUSES:
        raise ValueError("invalid_verification_status")
    data = {k: v for k, v in fields.items() if k in _SET_FIELDS and v is not None}
    if data:
        sets = ", ".join(f"{k} = :{k}" for k in data)
        conn.execute(text(f"UPDATE premiership SET {sets}, updated_at = now() WHERE id = :id"),
                     {**data, "id": premiership_id})
    after = get_premiership(conn, premiership_id)
    audit.write_audit(conn, workspace_id, actor, "premiership.update", entity="premiership",
                      entity_id=str(premiership_id), before=before, after=after)
    return after


def delete_premiership(conn: Connection, workspace_id: UUID, actor: str, premiership_id: UUID) -> None:
    before = get_premiership(conn, premiership_id)
    if before is None:
        raise ValueError("premiership_not_found")
    conn.execute(text("DELETE FROM premiership WHERE id = :id"), {"id": premiership_id})
    audit.write_audit(conn, workspace_id, actor, "premiership.delete", entity="premiership",
                      entity_id=str(premiership_id), before=before)


def detail(conn: Connection, premiership_id: UUID) -> dict[str, Any] | None:
    p = get_premiership(conn, premiership_id)
    if p is None:
        return None
    p["winners"] = list_winners(conn, premiership_id)
    return p


def validation_warnings(conn: Connection, premiership_id: UUID) -> list[str]:
    """Non-blocking consistency checks. A legitimate incomplete/historical premiership still saves."""
    p = get_premiership(conn, premiership_id)
    if p is None:
        raise ValueError("premiership_not_found")
    winners = list_winners(conn, premiership_id)
    warnings: list[str] = []
    if p["outcome"] == "awarded" and len(winners) == 0:
        warnings.append("awarded_premiership_no_winner")
    if p["outcome"] == "shared" and len(winners) < 2:
        warnings.append("shared_premiership_needs_two_winners")
    if p["outcome"] == "not_awarded" and len(winners) > 0:
        warnings.append("not_awarded_premiership_has_winner")
    # a winner with no evidence, no verification and no deciding series/match — flag for review,
    # never reject (a premiership must rest on verified results or recorded evidence).
    if (winners and p["verification_status"] in ("unverified", "provisional")
            and not p["evidence"] and p["deciding_series_id"] is None and p["deciding_match_id"] is None):
        warnings.append("premiership_unverified_no_evidence")
    return sorted(set(warnings))
