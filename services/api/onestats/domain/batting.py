"""Batting & dismissals (Phase 6, Stage 3).

A ``batting_entry`` is one batter's innings: order, identity, runs, balls, boundaries and the
dismissal (type + bowler/fielder attribution). The mapped ``dismissal_type`` is kept alongside the
preserved original ``dismissal_source_code`` (e.g. a CricketStatz ``Howout`` value) — the source
code is never overwritten, and unresolved codes stay unresolved.

Unknown is not zero: every statistic is nullable, so incomplete and newspaper-sourced cards record
only what is known. Validation is **non-blocking** — inconsistencies (an unresolved dismissal, a
bowler credited on a run-out) are returned as warnings so legitimate historical oddities still
save. Nothing is fabricated: a missing value is never inferred. Duplicate entries are prevented per
innings by player identity and by batting position.

Workspace-scoped (RLS); governed by ``match.manage``; audited.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain import audit

# Canonical dismissal vocabulary (deliverable 16 §16.8). Mirrors the CHECK in migration 0020.
DISMISSAL_TYPES = (
    "dnb", "absent",
    "not_out", "retired_not_out",
    "bowled", "caught", "caught_behind", "caught_and_bowled", "lbw",
    "stumped", "hit_wicket",
    "run_out", "retired_out", "obstructing", "hit_twice", "timed_out",
    "unknown_out",
    "retired", "unknown",
)

# Statuses that do NOT count as a wicket (fall) in the innings — no innings, not out, or
# unresolved. Everything else is a genuine dismissal; ``unknown_out`` counts (the batter was out).
NON_WICKET_STATUSES = ("dnb", "absent", "not_out", "retired_not_out", "retired", "unknown")

# Dismissals that credit a bowler (deliverable 16 §16.8). Run-outs and the other non-bowler
# dismissals credit no bowler; the statistics engine (later phase) enforces this — here we only
# surface a non-blocking warning when a bowler is attributed to a non-bowler dismissal.
BOWLER_CREDIT = ("bowled", "caught", "caught_behind", "caught_and_bowled", "lbw", "stumped", "hit_wicket")
# Dismissals that can carry a fielder/keeper attribution.
FIELDER_CREDIT = ("caught", "caught_behind", "caught_and_bowled", "run_out", "stumped")
# Unresolved statuses that should be confirmed before use in statistics — flagged, never guessed.
UNRESOLVED = ("retired", "unknown")

_COLS = (
    "id, workspace_id, innings_id, person_id, batting_position, runs, balls_faced, fours, sixes, "
    "minutes, dismissal_type, dismissal_source_code, bowler_person_id, fielder_person_id, notes, "
    "evidence, source_system, source_ref, created_at, updated_at"
)

_SET_FIELDS = (
    "person_id", "batting_position", "runs", "balls_faced", "fours", "sixes", "minutes",
    "dismissal_type", "dismissal_source_code", "bowler_person_id", "fielder_person_id",
    "notes", "evidence",
)


def get_entry(conn: Connection, entry_id: UUID) -> dict[str, Any] | None:
    r = conn.execute(
        text(f"SELECT {_COLS} FROM batting_entry WHERE id = :id"), {"id": entry_id}
    ).mappings().first()
    return dict(r) if r else None


def list_entries(conn: Connection, innings_id: UUID) -> list[dict[str, Any]]:
    """Entries for an innings in batting order (unknown positions last, then by creation)."""
    rows = conn.execute(
        text(f"SELECT {_COLS} FROM batting_entry WHERE innings_id = :i "
             "ORDER BY batting_position NULLS LAST, created_at"),
        {"i": innings_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def _innings_exists(conn: Connection, innings_id: UUID) -> bool:
    return conn.execute(text("SELECT 1 FROM innings WHERE id = :i"), {"i": innings_id}).first() is not None


def create_entry(
    conn: Connection, workspace_id: UUID, actor: str, *, innings_id: UUID,
    person_id: UUID | None = None, batting_position: int | None = None, runs: int | None = None,
    balls_faced: int | None = None, fours: int | None = None, sixes: int | None = None,
    minutes: int | None = None, dismissal_type: str | None = None,
    dismissal_source_code: str | None = None, bowler_person_id: UUID | None = None,
    fielder_person_id: UUID | None = None, notes: str | None = None, evidence: str | None = None,
    source_system: str | None = None, source_ref: str | None = None,
) -> UUID:
    if not _innings_exists(conn, innings_id):
        raise ValueError("innings_not_found")
    if dismissal_type is not None and dismissal_type not in DISMISSAL_TYPES:
        raise ValueError("invalid_dismissal_type")
    if batting_position is not None and batting_position < 1:
        raise ValueError("invalid_batting_position")
    # Clean duplicate errors (the partial unique indexes are the hard guard underneath).
    if person_id is not None and conn.execute(
        text("SELECT 1 FROM batting_entry WHERE innings_id = :i AND person_id = :p"),
        {"i": innings_id, "p": person_id},
    ).first() is not None:
        raise ValueError("duplicate_batter")
    if batting_position is not None and conn.execute(
        text("SELECT 1 FROM batting_entry WHERE innings_id = :i AND batting_position = :b"),
        {"i": innings_id, "b": batting_position},
    ).first() is not None:
        raise ValueError("duplicate_position")
    entry_id = conn.execute(
        text(
            "INSERT INTO batting_entry(workspace_id, innings_id, person_id, batting_position, runs, "
            " balls_faced, fours, sixes, minutes, dismissal_type, dismissal_source_code, "
            " bowler_person_id, fielder_person_id, notes, evidence, source_system, source_ref) "
            "VALUES (:w, :i, :p, :pos, :r, :bf, :f4, :f6, :min, :dt, :dsc, :bp, :fp, :notes, :ev, "
            " :ss, :sr) RETURNING id"
        ),
        {"w": workspace_id, "i": innings_id, "p": person_id, "pos": batting_position, "r": runs,
         "bf": balls_faced, "f4": fours, "f6": sixes, "min": minutes, "dt": dismissal_type,
         "dsc": dismissal_source_code, "bp": bowler_person_id, "fp": fielder_person_id,
         "notes": notes, "ev": evidence, "ss": source_system, "sr": source_ref},
    ).scalar_one()
    audit.write_audit(conn, workspace_id, actor, "batting_entry.create", entity="batting_entry",
                      entity_id=str(entry_id),
                      after={"innings_id": str(innings_id), "batting_position": batting_position,
                             "dismissal_type": dismissal_type})
    return entry_id


def update_entry(conn: Connection, workspace_id: UUID, actor: str, entry_id: UUID, **fields: Any) -> dict[str, Any]:
    before = get_entry(conn, entry_id)
    if before is None:
        raise ValueError("entry_not_found")
    if fields.get("dismissal_type") is not None and fields["dismissal_type"] not in DISMISSAL_TYPES:
        raise ValueError("invalid_dismissal_type")
    if fields.get("batting_position") is not None and fields["batting_position"] < 1:
        raise ValueError("invalid_batting_position")
    data = {k: v for k, v in fields.items() if k in _SET_FIELDS and v is not None}
    # Re-check duplicates against OTHER entries when identity/position change.
    if "person_id" in data and conn.execute(
        text("SELECT 1 FROM batting_entry WHERE innings_id = :i AND person_id = :p AND id <> :id"),
        {"i": before["innings_id"], "p": data["person_id"], "id": entry_id},
    ).first() is not None:
        raise ValueError("duplicate_batter")
    if "batting_position" in data and conn.execute(
        text("SELECT 1 FROM batting_entry WHERE innings_id = :i AND batting_position = :b AND id <> :id"),
        {"i": before["innings_id"], "b": data["batting_position"], "id": entry_id},
    ).first() is not None:
        raise ValueError("duplicate_position")
    if data:
        sets = ", ".join(f"{k} = :{k}" for k in data)
        conn.execute(text(f"UPDATE batting_entry SET {sets}, updated_at = now() WHERE id = :id"),
                     {**data, "id": entry_id})
    after = get_entry(conn, entry_id)
    audit.write_audit(conn, workspace_id, actor, "batting_entry.update", entity="batting_entry",
                      entity_id=str(entry_id), before=before, after=after)
    return after


def delete_entry(conn: Connection, workspace_id: UUID, actor: str, entry_id: UUID) -> None:
    before = get_entry(conn, entry_id)
    if before is None:
        raise ValueError("entry_not_found")
    conn.execute(text("DELETE FROM batting_entry WHERE id = :id"), {"id": entry_id})
    audit.write_audit(conn, workspace_id, actor, "batting_entry.delete", entity="batting_entry",
                      entity_id=str(entry_id), before=before)


def _sum_known(values: list[Any]) -> int | None:
    known = [v for v in values if v is not None]
    return sum(known) if known else None


def batting_card(conn: Connection, innings_id: UUID) -> dict[str, Any]:
    """Summary of the batting card. Totals sum only the KNOWN values (unknown is excluded, never
    treated as 0). ``runs_total`` is the batters' runs only — it excludes extras, which the innings
    total (Stage 2) adds. ``wickets`` counts genuine dismissals (``unknown_out`` included; not-out,
    dnb, absent and unresolved statuses excluded)."""
    rows = list_entries(conn, innings_id)
    runs_total = _sum_known([r["runs"] for r in rows])
    balls_total = _sum_known([r["balls_faced"] for r in rows])
    wickets = sum(
        1 for r in rows
        if r["dismissal_type"] is not None and r["dismissal_type"] not in NON_WICKET_STATUSES
    )
    batted = sum(1 for r in rows if r["dismissal_type"] not in ("dnb", "absent"))
    return {
        "innings_id": str(innings_id),
        "entries": len(rows),
        "batted": batted,
        "runs_total": runs_total,       # batters only; unknown runs excluded (not 0)
        "balls_total": balls_total,
        "wickets": wickets,             # genuine dismissals; unknown_out counts, not-out does not
    }


def validation_warnings(conn: Connection, innings_id: UUID) -> list[str]:
    """Non-blocking consistency checks across the batting card. Historical oddities still save."""
    rows = list_entries(conn, innings_id)
    warnings: list[str] = []
    for r in rows:
        dt = r["dismissal_type"]
        if dt in UNRESOLVED:
            warnings.append("dismissal_unresolved")
        if r["bowler_person_id"] is not None and dt is not None and dt not in BOWLER_CREDIT:
            warnings.append("bowler_on_non_bowler_dismissal")
        if r["fielder_person_id"] is not None and dt is not None and dt not in FIELDER_CREDIT:
            warnings.append("fielder_on_non_fielder_dismissal")
    if sum(1 for r in rows if r["dismissal_type"] is not None
           and r["dismissal_type"] not in NON_WICKET_STATUSES) > 10:
        warnings.append("more_than_10_wickets")
    return sorted(set(warnings))
