"""The authoritative international match-index register (Part C).

One row per international match that is EXPECTED to exist, carrying a stable internal id plus the
external ids by which allow-listed sources refer to it, and an explicit progress state. The register
is the source of truth for "what should exist" and is reconciled against >= 2 sources — a single site
is never trusted as proof of completeness.

Guarantees enforced here:
  * Duplicate prevention: an entry sharing ANY external source-ref with an incoming one is reused and
    its refs merged, so repeated discovery reconciles rather than duplicates.
  * Honest counts: ``indexed``/``imported``/``verified`` coverage counts are recomputed from real rows;
    ``expected`` is only ever set by an explicit reconciliation call (never derived, never fabricated),
    and stays NULL (unknown) until then.
  * Official-status gating: only ``recognised`` entries advance through the import states; ``candidate``
    and ``disputed`` are held for research and never auto-imported.
"""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain import audit

FORMATS = ("test", "odi", "t20i")
STATES = ("expected", "indexed", "imported", "complete", "verified")
OFFICIAL_STATUSES = ("recognised", "candidate", "disputed", "not_international")
COVERAGE_STATES = ("unknown", "searching", "partial", "reconciled", "failed")

_COLS = ("id, workspace_id, match_id, format, state, official_status, match_number, start_date, "
         "date_precision, team_a, team_b, venue_name, series, source_refs, source_agreement, "
         "confidence, notes, first_seen_at, last_reconciled_at, imported_at, verified_at")


def _get(conn: Connection, workspace_id: UUID, entry_id: UUID) -> dict[str, Any] | None:
    r = conn.execute(
        text(f"SELECT {_COLS} FROM match_index_entry WHERE id = :id AND workspace_id = :w"),
        {"id": entry_id, "w": workspace_id},
    ).mappings().first()
    return dict(r) if r else None


def find_by_source_ref(conn: Connection, workspace_id: UUID, source_system: str,
                       source_ref: str) -> dict[str, Any] | None:
    """The entry whose ``source_refs`` already maps ``source_system`` to ``source_ref`` (JSONB
    containment), or None. This is how re-discovery reconciles to the existing row."""
    r = conn.execute(
        text(f"SELECT {_COLS} FROM match_index_entry WHERE workspace_id = :w "
             f"AND source_refs @> CAST(:probe AS jsonb) LIMIT 1"),
        {"w": workspace_id, "probe": json.dumps({source_system: source_ref})},
    ).mappings().first()
    return dict(r) if r else None


def register(
    conn: Connection, workspace_id: UUID, actor: str, *, format: str,
    source_refs: dict[str, str], official_status: str = "recognised",
    match_number: int | None = None, start_date: Any = None, date_precision: str = "exact",
    team_a: str | None = None, team_b: str | None = None, venue_name: str | None = None,
    series: str | None = None, source_agreement: dict[str, Any] | None = None,
    confidence: float | None = None, notes: str | None = None,
) -> dict[str, Any]:
    """Register (or reconcile to) one expected international match. ``source_refs`` maps each source
    system to that source's id for this match; providing >= 2 is how completeness is evidenced.

    If an existing entry shares any of the given source-refs it is reused: its refs are merged and any
    still-missing provisional field is filled (existing non-null values are never overwritten here —
    corrections go through the approval workflow, not silent rewrites)."""
    if format not in FORMATS:
        raise ValueError("invalid_format")
    if official_status not in OFFICIAL_STATUSES:
        raise ValueError("invalid_official_status")
    if not source_refs:
        raise ValueError("source_refs_required")

    existing: dict[str, Any] | None = None
    for ss, ref in source_refs.items():
        existing = find_by_source_ref(conn, workspace_id, ss, ref)
        if existing is not None:
            break

    if existing is None:
        state = "indexed" if (start_date or team_a or match_number is not None) else "expected"
        eid = conn.execute(
            text("INSERT INTO match_index_entry(workspace_id, format, state, official_status, "
                 "match_number, start_date, date_precision, team_a, team_b, venue_name, series, "
                 "source_refs, source_agreement, confidence, notes, last_reconciled_at) "
                 "VALUES (:w, :f, :state, :os, :mn, :sd, :dp, :ta, :tb, :vn, :sr, "
                 "CAST(:refs AS jsonb), CAST(:agree AS jsonb), :conf, :notes, now()) RETURNING id"),
            {"w": workspace_id, "f": format, "state": state, "os": official_status, "mn": match_number,
             "sd": start_date, "dp": date_precision, "ta": team_a, "tb": team_b, "vn": venue_name,
             "sr": series, "refs": json.dumps(source_refs),
             "agree": json.dumps(source_agreement) if source_agreement is not None else None,
             "conf": confidence, "notes": notes},
        ).scalar_one()
        audit.write_audit(conn, workspace_id, actor, "match_index.register", entity="match_index_entry",
                          entity_id=str(eid), after={"format": format, "state": state,
                                                     "official_status": official_status, "source_refs": source_refs})
        return _get(conn, workspace_id, eid)  # type: ignore[return-value]

    merged = dict(existing["source_refs"] or {})
    merged.update(source_refs)
    conn.execute(
        text("UPDATE match_index_entry SET source_refs = CAST(:refs AS jsonb), "
             "source_agreement = COALESCE(CAST(:agree AS jsonb), source_agreement), "
             "match_number = COALESCE(match_number, :mn), start_date = COALESCE(start_date, :sd), "
             "team_a = COALESCE(team_a, :ta), team_b = COALESCE(team_b, :tb), "
             "venue_name = COALESCE(venue_name, :vn), series = COALESCE(series, :sr), "
             "confidence = COALESCE(:conf, confidence), last_reconciled_at = now(), updated_at = now() "
             "WHERE id = :id"),
        {"refs": json.dumps(merged),
         "agree": json.dumps(source_agreement) if source_agreement is not None else None,
         "mn": match_number, "sd": start_date, "ta": team_a, "tb": team_b, "vn": venue_name,
         "sr": series, "conf": confidence, "id": existing["id"]},
    )
    return _get(conn, workspace_id, existing["id"])  # type: ignore[return-value]


def link_match(conn: Connection, workspace_id: UUID, actor: str, entry_id: UUID, match_id: UUID, *,
               complete: bool = False) -> dict[str, Any]:
    """Link an imported match to its index entry and move it to ``imported`` (or ``complete``). Only a
    ``recognised`` entry may be imported — a candidate/disputed match must be resolved first."""
    entry = _get(conn, workspace_id, entry_id)
    if entry is None:
        raise ValueError("entry_not_found")
    if entry["official_status"] != "recognised":
        raise ValueError("not_recognised_cannot_import")
    state = "complete" if complete else "imported"
    conn.execute(
        text("UPDATE match_index_entry SET match_id = :mid, state = :state, "
             "imported_at = COALESCE(imported_at, now()), updated_at = now() WHERE id = :id"),
        {"mid": match_id, "state": state, "id": entry_id},
    )
    audit.write_audit(conn, workspace_id, actor, "match_index.link_match", entity="match_index_entry",
                      entity_id=str(entry_id), after={"match_id": str(match_id), "state": state})
    return _get(conn, workspace_id, entry_id)  # type: ignore[return-value]


def mark_verified(conn: Connection, workspace_id: UUID, actor: str, entry_id: UUID) -> dict[str, Any]:
    entry = _get(conn, workspace_id, entry_id)
    if entry is None:
        raise ValueError("entry_not_found")
    if entry["match_id"] is None:
        raise ValueError("cannot_verify_unimported")
    conn.execute(
        text("UPDATE match_index_entry SET state = 'verified', verified_at = now(), updated_at = now() "
             "WHERE id = :id"),
        {"id": entry_id},
    )
    audit.write_audit(conn, workspace_id, actor, "match_index.verified", entity="match_index_entry",
                      entity_id=str(entry_id))
    return _get(conn, workspace_id, entry_id)  # type: ignore[return-value]


def set_official_status(conn: Connection, workspace_id: UUID, actor: str, entry_id: UUID,
                        official_status: str, *, reason: str | None = None) -> dict[str, Any]:
    if official_status not in OFFICIAL_STATUSES:
        raise ValueError("invalid_official_status")
    entry = _get(conn, workspace_id, entry_id)
    if entry is None:
        raise ValueError("entry_not_found")
    conn.execute(
        text("UPDATE match_index_entry SET official_status = :os, "
             "notes = COALESCE(:reason, notes), updated_at = now() WHERE id = :id"),
        {"os": official_status, "reason": reason, "id": entry_id},
    )
    audit.write_audit(conn, workspace_id, actor, "match_index.official_status", entity="match_index_entry",
                      entity_id=str(entry_id), before={"official_status": entry["official_status"]},
                      after={"official_status": official_status})
    return _get(conn, workspace_id, entry_id)  # type: ignore[return-value]


# --- coverage (per format x period) ---------------------------------------------------------------

def recount_coverage(conn: Connection, workspace_id: UUID, format: str, period: str = "all") -> dict[str, Any]:
    """Recompute the GENUINE indexed/imported/verified counts for a scope from the actual rows. Leaves
    ``expected_count`` untouched (that is set only by :func:`set_expected`). ``period`` 'all' counts
    the whole format; a 4-digit year counts entries starting in that year."""
    where = "workspace_id = :w AND format = :f"
    params: dict[str, Any] = {"w": workspace_id, "f": format}
    if period != "all":
        where += " AND EXTRACT(YEAR FROM start_date) = :yr"
        params["yr"] = int(period)
    counts = conn.execute(
        text(f"SELECT count(*) FILTER (WHERE official_status = 'recognised') AS indexed, "
             f"count(*) FILTER (WHERE state IN ('imported','complete','verified')) AS imported, "
             f"count(*) FILTER (WHERE state = 'verified') AS verified "
             f"FROM match_index_entry WHERE {where}"),
        params,
    ).mappings().first()
    conn.execute(
        text("INSERT INTO match_index_coverage(workspace_id, format, period, indexed_count, "
             "imported_count, verified_count) VALUES (:w, :f, :p, :idx, :imp, :ver) "
             "ON CONFLICT ON CONSTRAINT uq_match_index_coverage DO UPDATE SET "
             "indexed_count = EXCLUDED.indexed_count, imported_count = EXCLUDED.imported_count, "
             "verified_count = EXCLUDED.verified_count, updated_at = now()"),
        {"w": workspace_id, "f": format, "p": period, "idx": counts["indexed"],
         "imp": counts["imported"], "ver": counts["verified"]},
    )
    return get_coverage(conn, workspace_id, format, period)  # type: ignore[return-value]


def set_expected(conn: Connection, workspace_id: UUID, actor: str, format: str, period: str, *,
                 expected_count: int, sources: dict[str, Any], coverage_state: str = "reconciled") -> dict[str, Any]:
    """Record an EXPECTED count for a scope — ONLY from an explicit reconciliation of >= 2 sources.
    ``sources`` is the provenance (which sources were consulted and what each claimed). An unknown
    count must not be passed here; leave it unset so it stays NULL (unknown), never zero."""
    if coverage_state not in COVERAGE_STATES:
        raise ValueError("invalid_coverage_state")
    if expected_count < 0:
        raise ValueError("expected_count_negative")
    if not sources or len(sources) < 2:
        # completeness is never evidenced by a single site
        raise ValueError("expected_requires_multiple_sources")
    conn.execute(
        text("INSERT INTO match_index_coverage(workspace_id, format, period, coverage_state, "
             "expected_count, sources, last_reconciled_at) "
             "VALUES (:w, :f, :p, :cs, :exp, CAST(:src AS jsonb), now()) "
             "ON CONFLICT ON CONSTRAINT uq_match_index_coverage DO UPDATE SET "
             "coverage_state = EXCLUDED.coverage_state, expected_count = EXCLUDED.expected_count, "
             "sources = EXCLUDED.sources, last_reconciled_at = now(), updated_at = now()"),
        {"w": workspace_id, "f": format, "p": period, "cs": coverage_state, "exp": expected_count,
         "src": json.dumps(sources)},
    )
    audit.write_audit(conn, workspace_id, actor, "match_index.set_expected", entity="match_index_coverage",
                      entity_id=f"{format}:{period}", after={"expected_count": expected_count,
                                                             "sources": list(sources.keys())})
    return recount_coverage(conn, workspace_id, format, period)


def get_coverage(conn: Connection, workspace_id: UUID, format: str, period: str = "all") -> dict[str, Any] | None:
    r = conn.execute(
        text("SELECT * FROM match_index_coverage WHERE workspace_id = :w AND format = :f AND period = :p"),
        {"w": workspace_id, "f": format, "p": period},
    ).mappings().first()
    return dict(r) if r else None


def summary(conn: Connection, workspace_id: UUID) -> dict[str, Any]:
    """Per-format register summary for the dashboard — GENUINE counts straight from the rows.
    ``expected`` is reported as the reconciled coverage figure where one exists, else None (unknown,
    never fabricated as a total)."""
    out: dict[str, Any] = {}
    for fmt in FORMATS:
        rows = conn.execute(
            text("SELECT state, official_status, count(*) AS n FROM match_index_entry "
                 "WHERE workspace_id = :w AND format = :f GROUP BY state, official_status"),
            {"w": workspace_id, "f": fmt},
        ).mappings().all()
        by_state = {s: 0 for s in STATES}
        candidates = disputed = 0
        for r in rows:
            if r["official_status"] == "recognised":
                by_state[r["state"]] = by_state.get(r["state"], 0) + r["n"]
            elif r["official_status"] == "candidate":
                candidates += r["n"]
            elif r["official_status"] == "disputed":
                disputed += r["n"]
        cov = get_coverage(conn, workspace_id, fmt, "all")
        out[fmt] = {
            "states": by_state,
            "candidates": candidates,
            "disputed": disputed,
            "expected": cov["expected_count"] if cov else None,  # None = unknown (NOT zero)
            "coverage_state": cov["coverage_state"] if cov else "unknown",
        }
    return out
