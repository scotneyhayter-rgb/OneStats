"""Fall of wicket & partnerships (Phase 6, Stage 5).

Two closely-related records nested under an innings:

* **Fall of wicket** — the wicket number, the team score at the fall, the dismissed batter and
  not-out partner where known, the over at the fall, and a link to the dismissed batter's
  ``batting_entry``.
* **Batting partnership** — the wicket it is for, runs/balls, the two participants, whether it was
  unbroken, and how it ended (``end_reason``), so a retirement is recorded as such rather than
  forced into a wicket.

Nothing is invented: every statistic is nullable (unknown ≠ zero), incomplete historical cards are
allowed, and inconsistencies are returned as **non-blocking warnings**. Source values and evidence
are preserved; all writes are audited.

**Bowling partnerships** (the OneStats statistical report over groups of 2–4 bowlers) are a
different concept from batting partnerships and are **not** stored here. ``bowling_partnership_
inputs`` exposes the atomic building block the future report needs — the bowlers who bowled for a
side in an innings, with their credited-wicket counts — but the records calculation itself (which
counts wickets credited to all nominated bowlers in matches where they all played for the same
team) is deferred to the statistics phase (deliverable 25).

Workspace-scoped (RLS); governed by ``match.manage``.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain import audit
from onestats.domain.batting import BOWLER_CREDIT, NON_WICKET_STATUSES

END_REASONS = ("wicket", "retired", "declared", "forfeited", "innings_closed", "unknown")

_FOW_COLS = (
    "id, workspace_id, innings_id, wicket_number, team_score, dismissed_person_id, "
    "not_out_person_id, batting_entry_id, overs_text, legal_balls, notes, evidence, "
    "source_system, source_ref, created_at, updated_at"
)
_FOW_SET = ("wicket_number", "team_score", "dismissed_person_id", "not_out_person_id",
            "batting_entry_id", "overs_text", "legal_balls", "notes", "evidence")

_PART_COLS = (
    "id, workspace_id, innings_id, wicket_number, runs, balls, player1_person_id, "
    "player2_person_id, unbroken, end_reason, notes, evidence, source_system, source_ref, "
    "created_at, updated_at"
)
_PART_SET = ("wicket_number", "runs", "balls", "player1_person_id", "player2_person_id",
             "unbroken", "end_reason", "notes", "evidence")


def _innings_exists(conn: Connection, innings_id: UUID) -> bool:
    return conn.execute(text("SELECT 1 FROM innings WHERE id = :i"), {"i": innings_id}).first() is not None


# ----- fall of wicket -------------------------------------------------------------------------

def get_fow(conn: Connection, fow_id: UUID) -> dict[str, Any] | None:
    r = conn.execute(text(f"SELECT {_FOW_COLS} FROM fall_of_wicket WHERE id = :id"),
                     {"id": fow_id}).mappings().first()
    return dict(r) if r else None


def list_fow(conn: Connection, innings_id: UUID) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(f"SELECT {_FOW_COLS} FROM fall_of_wicket WHERE innings_id = :i "
             "ORDER BY wicket_number NULLS LAST, created_at"),
        {"i": innings_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def create_fow(
    conn: Connection, workspace_id: UUID, actor: str, *, innings_id: UUID,
    wicket_number: int | None = None, team_score: int | None = None,
    dismissed_person_id: UUID | None = None, not_out_person_id: UUID | None = None,
    batting_entry_id: UUID | None = None, overs_text: str | None = None,
    legal_balls: int | None = None, notes: str | None = None, evidence: str | None = None,
    source_system: str | None = None, source_ref: str | None = None,
) -> UUID:
    if not _innings_exists(conn, innings_id):
        raise ValueError("innings_not_found")
    if wicket_number is not None and wicket_number < 1:
        raise ValueError("invalid_wicket_number")
    if wicket_number is not None and conn.execute(
        text("SELECT 1 FROM fall_of_wicket WHERE innings_id = :i AND wicket_number = :n"),
        {"i": innings_id, "n": wicket_number},
    ).first() is not None:
        raise ValueError("duplicate_wicket_number")
    fow_id = conn.execute(
        text(
            "INSERT INTO fall_of_wicket(workspace_id, innings_id, wicket_number, team_score, "
            " dismissed_person_id, not_out_person_id, batting_entry_id, overs_text, legal_balls, "
            " notes, evidence, source_system, source_ref) "
            "VALUES (:w, :i, :n, :ts, :dp, :np, :be, :ot, :lb, :notes, :ev, :ss, :sr) RETURNING id"
        ),
        {"w": workspace_id, "i": innings_id, "n": wicket_number, "ts": team_score,
         "dp": dismissed_person_id, "np": not_out_person_id, "be": batting_entry_id,
         "ot": overs_text, "lb": legal_balls, "notes": notes, "ev": evidence,
         "ss": source_system, "sr": source_ref},
    ).scalar_one()
    audit.write_audit(conn, workspace_id, actor, "fall_of_wicket.create", entity="fall_of_wicket",
                      entity_id=str(fow_id),
                      after={"innings_id": str(innings_id), "wicket_number": wicket_number,
                             "team_score": team_score})
    return fow_id


def update_fow(conn: Connection, workspace_id: UUID, actor: str, fow_id: UUID, **fields: Any) -> dict[str, Any]:
    before = get_fow(conn, fow_id)
    if before is None:
        raise ValueError("fow_not_found")
    if fields.get("wicket_number") is not None and fields["wicket_number"] < 1:
        raise ValueError("invalid_wicket_number")
    data = {k: v for k, v in fields.items() if k in _FOW_SET and v is not None}
    if "wicket_number" in data and conn.execute(
        text("SELECT 1 FROM fall_of_wicket WHERE innings_id = :i AND wicket_number = :n AND id <> :id"),
        {"i": before["innings_id"], "n": data["wicket_number"], "id": fow_id},
    ).first() is not None:
        raise ValueError("duplicate_wicket_number")
    if data:
        sets = ", ".join(f"{k} = :{k}" for k in data)
        conn.execute(text(f"UPDATE fall_of_wicket SET {sets}, updated_at = now() WHERE id = :id"),
                     {**data, "id": fow_id})
    after = get_fow(conn, fow_id)
    audit.write_audit(conn, workspace_id, actor, "fall_of_wicket.update", entity="fall_of_wicket",
                      entity_id=str(fow_id), before=before, after=after)
    return after


def delete_fow(conn: Connection, workspace_id: UUID, actor: str, fow_id: UUID) -> None:
    before = get_fow(conn, fow_id)
    if before is None:
        raise ValueError("fow_not_found")
    conn.execute(text("DELETE FROM fall_of_wicket WHERE id = :id"), {"id": fow_id})
    audit.write_audit(conn, workspace_id, actor, "fall_of_wicket.delete", entity="fall_of_wicket",
                      entity_id=str(fow_id), before=before)


# ----- partnerships ---------------------------------------------------------------------------

def get_partnership(conn: Connection, pid: UUID) -> dict[str, Any] | None:
    r = conn.execute(text(f"SELECT {_PART_COLS} FROM partnership WHERE id = :id"),
                     {"id": pid}).mappings().first()
    return dict(r) if r else None


def list_partnerships(conn: Connection, innings_id: UUID) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(f"SELECT {_PART_COLS} FROM partnership WHERE innings_id = :i "
             "ORDER BY wicket_number NULLS LAST, created_at"),
        {"i": innings_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def create_partnership(
    conn: Connection, workspace_id: UUID, actor: str, *, innings_id: UUID,
    wicket_number: int | None = None, runs: int | None = None, balls: int | None = None,
    player1_person_id: UUID | None = None, player2_person_id: UUID | None = None,
    unbroken: bool | None = None, end_reason: str | None = None, notes: str | None = None,
    evidence: str | None = None, source_system: str | None = None, source_ref: str | None = None,
) -> UUID:
    if not _innings_exists(conn, innings_id):
        raise ValueError("innings_not_found")
    if wicket_number is not None and wicket_number < 1:
        raise ValueError("invalid_wicket_number")
    if end_reason is not None and end_reason not in END_REASONS:
        raise ValueError("invalid_end_reason")
    if (player1_person_id is not None and player2_person_id is not None
            and player1_person_id == player2_person_id):
        raise ValueError("players_must_differ")
    pid = conn.execute(
        text(
            "INSERT INTO partnership(workspace_id, innings_id, wicket_number, runs, balls, "
            " player1_person_id, player2_person_id, unbroken, end_reason, notes, evidence, "
            " source_system, source_ref) "
            "VALUES (:w, :i, :n, :r, :b, :p1, :p2, :ub, :er, :notes, :ev, :ss, :sr) RETURNING id"
        ),
        {"w": workspace_id, "i": innings_id, "n": wicket_number, "r": runs, "b": balls,
         "p1": player1_person_id, "p2": player2_person_id, "ub": unbroken, "er": end_reason,
         "notes": notes, "ev": evidence, "ss": source_system, "sr": source_ref},
    ).scalar_one()
    audit.write_audit(conn, workspace_id, actor, "partnership.create", entity="partnership",
                      entity_id=str(pid),
                      after={"innings_id": str(innings_id), "wicket_number": wicket_number, "runs": runs})
    return pid


def update_partnership(conn: Connection, workspace_id: UUID, actor: str, pid: UUID, **fields: Any) -> dict[str, Any]:
    before = get_partnership(conn, pid)
    if before is None:
        raise ValueError("partnership_not_found")
    if fields.get("wicket_number") is not None and fields["wicket_number"] < 1:
        raise ValueError("invalid_wicket_number")
    if fields.get("end_reason") is not None and fields["end_reason"] not in END_REASONS:
        raise ValueError("invalid_end_reason")
    data = {k: v for k, v in fields.items() if k in _PART_SET and v is not None}
    p1 = data.get("player1_person_id", before["player1_person_id"])
    p2 = data.get("player2_person_id", before["player2_person_id"])
    if p1 is not None and p2 is not None and p1 == p2:
        raise ValueError("players_must_differ")
    if data:
        sets = ", ".join(f"{k} = :{k}" for k in data)
        conn.execute(text(f"UPDATE partnership SET {sets}, updated_at = now() WHERE id = :id"),
                     {**data, "id": pid})
    after = get_partnership(conn, pid)
    audit.write_audit(conn, workspace_id, actor, "partnership.update", entity="partnership",
                      entity_id=str(pid), before=before, after=after)
    return after


def delete_partnership(conn: Connection, workspace_id: UUID, actor: str, pid: UUID) -> None:
    before = get_partnership(conn, pid)
    if before is None:
        raise ValueError("partnership_not_found")
    conn.execute(text("DELETE FROM partnership WHERE id = :id"), {"id": pid})
    audit.write_audit(conn, workspace_id, actor, "partnership.delete", entity="partnership",
                      entity_id=str(pid), before=before)


# ----- reconciliation (non-blocking) ----------------------------------------------------------

def _sum_known(values: list[Any]) -> int | None:
    known = [v for v in values if v is not None]
    return sum(known) if known else None


def _derived_wickets(conn: Connection, innings_id: UUID) -> int:
    non_wicket = ", ".join(f"'{s}'" for s in NON_WICKET_STATUSES)
    return conn.execute(
        text(f"SELECT count(*) FROM batting_entry WHERE innings_id = :i "
             f"AND dismissal_type IS NOT NULL AND dismissal_type NOT IN ({non_wicket})"),
        {"i": innings_id},
    ).scalar_one()


def validation_warnings(conn: Connection, innings_id: UUID) -> list[str]:
    """Advisory checks across FOW, partnerships, batting and the innings total. Never blocks."""
    warnings: list[str] = []
    fows = list_fow(conn, innings_id)
    parts = list_partnerships(conn, innings_id)

    # FOW team scores should not decrease as wickets fall (Law 18 — the total only rises).
    scored = [(f["wicket_number"], f["team_score"]) for f in fows
              if f["wicket_number"] is not None and f["team_score"] is not None]
    scored.sort()
    if any(scored[i][1] < scored[i - 1][1] for i in range(1, len(scored))):
        warnings.append("fow_scores_not_increasing")
    if any(f["wicket_number"] is not None and f["wicket_number"] > 10 for f in fows):
        warnings.append("fow_wicket_number_gt_10")

    # FOW count vs genuine dismissals (Stage 3) — informational, both kept.
    derived = _derived_wickets(conn, innings_id)
    if fows and derived and len(fows) != derived:
        warnings.append("fow_count_differs_from_wickets")

    # more than one stand for the same wicket is legal (a retirement) but worth flagging.
    seen: set[int] = set()
    for p in parts:
        n = p["wicket_number"]
        if n is not None and n in seen:
            warnings.append("multiple_partnerships_same_wicket")
        if n is not None:
            seen.add(n)

    # partnership runs vs the innings batting+extras total — informational, only when known.
    part_runs = _sum_known([p["runs"] for p in parts])
    if part_runs is not None:
        inn = conn.execute(
            text("SELECT official_total FROM innings WHERE id = :i"), {"i": innings_id}
        ).mappings().first()
        if inn and inn["official_total"] is not None and part_runs != inn["official_total"]:
            warnings.append("partnership_runs_unreconciled")

    return sorted(set(warnings))


# ----- bowling-partnership compatibility (building block only; calc deferred) -----------------

def bowling_partnership_inputs(conn: Connection, innings_id: UUID) -> list[dict[str, Any]]:
    """Atomic input for the future bowling-partnership statistical report (deliverable 25): the
    bowlers who bowled for the fielding side in this innings, each with the number of wickets
    clearly credited to them (bowler-credit dismissals with a resolved bowler only).

    This is **not** a batting partnership and does **not** compute the report — grouping bowlers
    into 2/3/4-combinations and counting across matches where they all played for the same team is
    the statistics phase's job. It exists so Stage 5 can prove the data model supports it."""
    bowling_team_id = conn.execute(
        text("SELECT bowling_team_id FROM innings WHERE id = :i"), {"i": innings_id}
    ).scalar_one_or_none()
    credit = ", ".join(f"'{c}'" for c in BOWLER_CREDIT)
    rows = conn.execute(
        text(
            "SELECT be.person_id, "
            " (SELECT count(*) FROM batting_entry bt WHERE bt.innings_id = be.innings_id "
            f"   AND bt.bowler_person_id = be.person_id AND bt.dismissal_type IN ({credit})) "
            "   AS credited_wickets "
            "FROM bowling_entry be WHERE be.innings_id = :i AND be.person_id IS NOT NULL "
            "ORDER BY be.bowling_order NULLS LAST, be.created_at"
        ),
        {"i": innings_id},
    ).mappings().all()
    return [{"person_id": r["person_id"], "bowling_team_id": bowling_team_id,
             "credited_wickets": r["credited_wickets"]} for r in rows]
