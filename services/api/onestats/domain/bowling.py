"""Bowling (Phase 6, Stage 4).

A ``bowling_entry`` is one bowler's figures in an innings: identity, order, overs, maidens, runs
conceded, wickets credited, and attributed wides/no-balls. The original CricketStatz bowling-type
code is preserved verbatim (``bowling_type_raw``); unresolved codes stay unresolved.

**Overs are never decimals.** ``overs_text`` keeps the original notation (``'5.3'`` = 5 overs and
3 balls) and ``legal_balls`` is the canonical underlying legal-delivery count. Conversion uses the
match's ``balls_per_over`` (Law 17), read from playing conditions at calculation time — never a
hardcoded 6. Where ``balls_per_over`` is unknown, conversions and over-limit checks stay unknown
rather than assuming a modern default (no retrospective application, deliverable 39.5).

Recorded vs calculated are kept distinct (deliverable 13.6): ``wickets`` here is the **recorded**
figure, while ``derived_wickets`` is counted from the Stage-3 dismissal attribution (bowler-credit
modes with a resolved bowler only). Wickets are **never** auto-assigned to a bowler when the
dismissal is incomplete or ambiguous.

Validation is **non-blocking**: inconsistencies are warnings so incomplete historical figures still
save. Unknown is never zero. Workspace-scoped (RLS); governed by ``match.manage``; audited.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain import audit, matches
from onestats.domain.batting import BOWLER_CREDIT

_COLS = (
    "id, workspace_id, innings_id, person_id, bowling_order, overs_text, legal_balls, maidens, "
    "runs_conceded, wickets, wides, noballs, bowling_type_raw, notes, evidence, source_system, "
    "source_ref, created_at, updated_at"
)

_SET_FIELDS = (
    "person_id", "bowling_order", "overs_text", "legal_balls", "maidens", "runs_conceded",
    "wickets", "wides", "noballs", "bowling_type_raw", "notes", "evidence",
)


# ----- overs <-> legal balls (cricket-over notation, never decimal) ---------------------------

def legal_balls_from_notation(overs_text: str, balls_per_over: int) -> int | None:
    """Convert ``'O'`` or ``'O.B'`` cricket-over notation to a legal-ball count, given
    balls-per-over. Returns None when the text is not valid notation or ``B`` >= balls_per_over
    (an inconsistency the caller surfaces as a warning rather than a silently wrong number)."""
    if balls_per_over is None or balls_per_over <= 0:
        return None
    s = (overs_text or "").strip()
    if not s:
        return None
    try:
        if "." in s:
            whole, part = s.split(".", 1)
            overs = int(whole)
            balls = int(part)
        else:
            overs = int(s)
            balls = 0
    except ValueError:
        return None
    if overs < 0 or balls < 0 or balls >= balls_per_over:
        return None
    return overs * balls_per_over + balls


def notation_from_legal_balls(legal_balls: int | None, balls_per_over: int | None) -> str | None:
    if legal_balls is None or balls_per_over is None or balls_per_over <= 0:
        return None
    return f"{legal_balls // balls_per_over}.{legal_balls % balls_per_over}"


def _balls_per_over(conn: Connection, innings_id: UUID) -> int | None:
    """Resolve balls-per-over for the innings' match from playing conditions (None if unknown)."""
    match_id = conn.execute(
        text("SELECT match_id FROM innings WHERE id = :i"), {"i": innings_id}
    ).scalar_one_or_none()
    if match_id is None:
        return None
    return matches.effective_conditions(conn, match_id)["conditions"].get("balls_per_over")


def _overs_limit(conn: Connection, innings_id: UUID) -> int | None:
    match_id = conn.execute(
        text("SELECT match_id FROM innings WHERE id = :i"), {"i": innings_id}
    ).scalar_one_or_none()
    if match_id is None:
        return None
    return matches.effective_conditions(conn, match_id)["conditions"].get("overs_limit")


# ----- CRUD -----------------------------------------------------------------------------------

def get_entry(conn: Connection, entry_id: UUID) -> dict[str, Any] | None:
    r = conn.execute(
        text(f"SELECT {_COLS} FROM bowling_entry WHERE id = :id"), {"id": entry_id}
    ).mappings().first()
    return dict(r) if r else None


def list_entries(conn: Connection, innings_id: UUID) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(f"SELECT {_COLS} FROM bowling_entry WHERE innings_id = :i "
             "ORDER BY bowling_order NULLS LAST, created_at"),
        {"i": innings_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def _innings_exists(conn: Connection, innings_id: UUID) -> bool:
    return conn.execute(text("SELECT 1 FROM innings WHERE id = :i"), {"i": innings_id}).first() is not None


def create_entry(
    conn: Connection, workspace_id: UUID, actor: str, *, innings_id: UUID,
    person_id: UUID | None = None, bowling_order: int | None = None, overs_text: str | None = None,
    legal_balls: int | None = None, maidens: int | None = None, runs_conceded: int | None = None,
    wickets: int | None = None, wides: int | None = None, noballs: int | None = None,
    bowling_type_raw: str | None = None, notes: str | None = None, evidence: str | None = None,
    source_system: str | None = None, source_ref: str | None = None,
) -> UUID:
    if not _innings_exists(conn, innings_id):
        raise ValueError("innings_not_found")
    if bowling_order is not None and bowling_order < 1:
        raise ValueError("invalid_bowling_order")
    if wickets is not None and not (0 <= wickets <= 10):
        raise ValueError("invalid_wickets")
    # Derive legal_balls from the original notation only when it is not supplied directly and the
    # balls-per-over is known. The original notation is always preserved verbatim.
    if legal_balls is None and overs_text is not None:
        bpo = _balls_per_over(conn, innings_id)
        if bpo is not None:
            legal_balls = legal_balls_from_notation(overs_text, bpo)
    if person_id is not None and conn.execute(
        text("SELECT 1 FROM bowling_entry WHERE innings_id = :i AND person_id = :p"),
        {"i": innings_id, "p": person_id},
    ).first() is not None:
        raise ValueError("duplicate_bowler")
    if bowling_order is not None and conn.execute(
        text("SELECT 1 FROM bowling_entry WHERE innings_id = :i AND bowling_order = :b"),
        {"i": innings_id, "b": bowling_order},
    ).first() is not None:
        raise ValueError("duplicate_order")
    entry_id = conn.execute(
        text(
            "INSERT INTO bowling_entry(workspace_id, innings_id, person_id, bowling_order, "
            " overs_text, legal_balls, maidens, runs_conceded, wickets, wides, noballs, "
            " bowling_type_raw, notes, evidence, source_system, source_ref) "
            "VALUES (:w, :i, :p, :ord, :ot, :lb, :m, :rc, :wk, :wd, :nb, :bt, :notes, :ev, :ss, :sr) "
            "RETURNING id"
        ),
        {"w": workspace_id, "i": innings_id, "p": person_id, "ord": bowling_order, "ot": overs_text,
         "lb": legal_balls, "m": maidens, "rc": runs_conceded, "wk": wickets, "wd": wides,
         "nb": noballs, "bt": bowling_type_raw, "notes": notes, "ev": evidence, "ss": source_system,
         "sr": source_ref},
    ).scalar_one()
    audit.write_audit(conn, workspace_id, actor, "bowling_entry.create", entity="bowling_entry",
                      entity_id=str(entry_id),
                      after={"innings_id": str(innings_id), "bowling_order": bowling_order,
                             "wickets": wickets})
    return entry_id


def update_entry(conn: Connection, workspace_id: UUID, actor: str, entry_id: UUID, **fields: Any) -> dict[str, Any]:
    before = get_entry(conn, entry_id)
    if before is None:
        raise ValueError("entry_not_found")
    if fields.get("bowling_order") is not None and fields["bowling_order"] < 1:
        raise ValueError("invalid_bowling_order")
    if fields.get("wickets") is not None and not (0 <= fields["wickets"] <= 10):
        raise ValueError("invalid_wickets")
    # A field present with value None means "clear it" (every scorecard column is nullable — unknown
    # is not zero); only fields the caller actually passed are present, so absent = unchanged.
    data = {k: v for k, v in fields.items() if k in _SET_FIELDS}
    # Re-derive legal_balls if the notation changed and no explicit legal_balls was given.
    if "overs_text" in data and "legal_balls" not in data:
        bpo = _balls_per_over(conn, before["innings_id"])
        if bpo is not None:
            derived = legal_balls_from_notation(data["overs_text"], bpo)
            if derived is not None:
                data["legal_balls"] = derived
    if "person_id" in data and conn.execute(
        text("SELECT 1 FROM bowling_entry WHERE innings_id = :i AND person_id = :p AND id <> :id"),
        {"i": before["innings_id"], "p": data["person_id"], "id": entry_id},
    ).first() is not None:
        raise ValueError("duplicate_bowler")
    if "bowling_order" in data and conn.execute(
        text("SELECT 1 FROM bowling_entry WHERE innings_id = :i AND bowling_order = :b AND id <> :id"),
        {"i": before["innings_id"], "b": data["bowling_order"], "id": entry_id},
    ).first() is not None:
        raise ValueError("duplicate_order")
    if data:
        sets = ", ".join(f"{k} = :{k}" for k in data)
        conn.execute(text(f"UPDATE bowling_entry SET {sets}, updated_at = now() WHERE id = :id"),
                     {**data, "id": entry_id})
    after = get_entry(conn, entry_id)
    audit.write_audit(conn, workspace_id, actor, "bowling_entry.update", entity="bowling_entry",
                      entity_id=str(entry_id), before=before, after=after)
    return after


def delete_entry(conn: Connection, workspace_id: UUID, actor: str, entry_id: UUID) -> None:
    before = get_entry(conn, entry_id)
    if before is None:
        raise ValueError("entry_not_found")
    conn.execute(text("DELETE FROM bowling_entry WHERE id = :id"), {"id": entry_id})
    audit.write_audit(conn, workspace_id, actor, "bowling_entry.delete", entity="bowling_entry",
                      entity_id=str(entry_id), before=before)


# ----- figures & reconciliation ---------------------------------------------------------------

def _sum_known(values: list[Any]) -> int | None:
    known = [v for v in values if v is not None]
    return sum(known) if known else None


def _derived_bowler_wickets(conn: Connection, innings_id: UUID) -> int:
    """Wickets creditable to bowlers from the Stage-3 dismissals: bowler-credit modes with a
    resolved bowler only. Incomplete/ambiguous dismissals are never auto-credited."""
    credit = ", ".join(f"'{c}'" for c in BOWLER_CREDIT)
    return conn.execute(
        text(f"SELECT count(*) FROM batting_entry WHERE innings_id = :i "
             f"AND bowler_person_id IS NOT NULL AND dismissal_type IN ({credit})"),
        {"i": innings_id},
    ).scalar_one()


def bowling_card(conn: Connection, innings_id: UUID) -> dict[str, Any]:
    """Recorded bowling figures plus the separately-calculated cross-checks (deliverable 13.6)."""
    rows = list_entries(conn, innings_id)
    bpo = _balls_per_over(conn, innings_id)
    return {
        "innings_id": str(innings_id),
        "entries": len(rows),
        "balls_per_over": bpo,
        # recorded (as entered) — unknown values excluded, never treated as 0
        "recorded_wickets": _sum_known([r["wickets"] for r in rows]),
        "recorded_runs_conceded": _sum_known([r["runs_conceded"] for r in rows]),
        "recorded_maidens": _sum_known([r["maidens"] for r in rows]),
        "total_legal_balls": _sum_known([r["legal_balls"] for r in rows]),
        "total_overs": notation_from_legal_balls(_sum_known([r["legal_balls"] for r in rows]), bpo),
        # calculated from verified underlying data (Stage 3 dismissals) — kept distinct
        "derived_bowler_wickets": _derived_bowler_wickets(conn, innings_id),
    }


def validation_warnings(conn: Connection, innings_id: UUID) -> list[str]:
    """Non-blocking reconciliation against the innings (Stage 2) and batting (Stage 3) records."""
    rows = list_entries(conn, innings_id)
    warnings: list[str] = []
    bpo = _balls_per_over(conn, innings_id)
    overs_limit = _overs_limit(conn, innings_id)

    recorded_wkts = _sum_known([r["wickets"] for r in rows])
    if recorded_wkts is not None and recorded_wkts > 10:
        warnings.append("bowling_wickets_exceed_10")
    derived = _derived_bowler_wickets(conn, innings_id)
    if recorded_wkts is not None and derived and recorded_wkts != derived:
        warnings.append("bowling_wickets_differ_from_dismissals")  # informational; both kept

    for r in rows:
        # overs notation vs the stored legal-ball count, given balls-per-over
        if (r["overs_text"] and r["legal_balls"] is not None and bpo
                and legal_balls_from_notation(r["overs_text"], bpo) != r["legal_balls"]):
            warnings.append("overs_notation_inconsistent")
        # maidens cannot exceed completed overs (Law 17), when both are known
        if (r["maidens"] is not None and r["legal_balls"] is not None and bpo
                and r["maidens"] > r["legal_balls"] // bpo):
            warnings.append("maidens_exceed_overs")
        # innings overs limit (playing condition, Law 17) — advisory, never assume a default
        if (r["legal_balls"] is not None and overs_limit is not None and bpo
                and r["legal_balls"] > overs_limit * bpo):
            warnings.append("overs_exceed_limit")

    # runs reconciliation: bowlers' runs conceded + byes + leg-byes + penalty should match the
    # innings total (byes/leg-byes are not charged to bowlers). Advisory, only when all known.
    total_conceded = _sum_known([r["runs_conceded"] for r in rows])
    if total_conceded is not None:
        inn = conn.execute(
            text("SELECT byes, legbyes, penalty, official_total FROM innings WHERE id = :i"),
            {"i": innings_id},
        ).mappings().first()
        if inn and inn["official_total"] is not None:
            non_bowler = _sum_known([inn["byes"], inn["legbyes"], inn["penalty"]]) or 0
            if total_conceded + non_bowler != inn["official_total"]:
                warnings.append("bowling_runs_unreconciled")  # informational

    return sorted(set(warnings))
