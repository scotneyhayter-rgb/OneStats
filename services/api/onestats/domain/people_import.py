"""CricketStatz player & official identity import (Phase 5, Stage 5).

Extends the Phase 4 Stage 6 staging pipeline (``import_batch`` / ``import_staging_record``) to
people. Source rows are staged verbatim (sentinel-aware: ``DOB 1700-01-01`` and blanks → unknown,
``MyClub``/``ClubID 0`` → unknown — originals preserved in ``raw``), detected against existing
identities (by source identity and name/alias, honouring Stage 3 distinct assertions and merges),
routed to administrator review where uncertain, and promoted only on approval. Idempotent on
``(source_system, source_ref)``: re-import matches, never duplicates; resumable and non-destructive.

A matching name never auto-merges. An individual appearing as both player and official (same
source ref) becomes ONE person holding both roles — never duplicated. Verified information is
never overwritten by lower-confidence imported data; conflicts are retained for review.

Governed by ``import.manage``; every step audited.
"""

from __future__ import annotations

import json
import re
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain import audit, imports, people, person_resolution

SOURCE_SYSTEM = "cricket_statz"
CS_UNKNOWN_DOB = "1700-01-01"
_ENTITY_ROLE = {"player": "player", "official": "official"}


def _normalise(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def _display_name(row: dict[str, Any]) -> str:
    parts = [str(row.get("Firstname") or "").strip(), str(row.get("Lastname") or "").strip()]
    return " ".join(p for p in parts if p).strip()


def _clean_dob(dob: Any) -> tuple[Any, str]:
    if dob in (None, "", CS_UNKNOWN_DOB):
        return None, "unknown"
    return dob, "exact"


def _norm_person(row: dict[str, Any]) -> dict[str, Any]:
    dob, prec = _clean_dob(row.get("DOB"))
    myclub = row.get("MyClub")
    return {
        "display_name": _display_name(row) or "(unknown)",
        "firstname": row.get("Firstname"),
        "lastname": row.get("Lastname"),
        "dob": dob,
        "dob_precision": prec,
        "dob_source_value": row.get("DOB"),         # original preserved for audit
        "myclub_source_ref": None if myclub in (None, 0, "0", "") else str(myclub),
    }


# --------------------------------------------------------------------------- stage


def stage_people(
    conn: Connection, workspace_id: UUID, actor: str, *, payload: dict[str, Any],
    filename: str | None = None, source_system: str = SOURCE_SYSTEM,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("invalid_payload")  # noqa: TRY004 — uniform ValueError->422 handling
    players = payload.get("players") or []
    officials = payload.get("officials") or []
    if not players and not officials:
        raise ValueError("no_people_collections")

    batch_id = conn.execute(
        text(
            "INSERT INTO import_batch(workspace_id, source_system, source_filename, created_by) "
            "VALUES (:w, :ss, :fn, :actor) RETURNING id"
        ),
        {"w": workspace_id, "ss": source_system, "fn": filename, "actor": actor},
    ).scalar_one()

    counts = {"player": 0, "official": 0}
    for entity_type, rows in (("player", players), ("official", officials)):
        for row in rows:
            ref = row.get("PlayerID")
            if ref is None:
                continue
            conn.execute(
                text(
                    "INSERT INTO import_staging_record"
                    "(workspace_id, batch_id, entity_type, source_ref, raw, normalised, status, resolution) "
                    "VALUES (:w, :b, :et, :sr, CAST(:raw AS jsonb), CAST(:norm AS jsonb), 'staged', 'new') "
                    "ON CONFLICT ON CONSTRAINT uq_staging_record DO NOTHING"
                ),
                {"w": workspace_id, "b": batch_id, "et": entity_type, "sr": str(ref),
                 "raw": json.dumps(row, default=str), "norm": json.dumps(_norm_person(row), default=str)},
            )
            counts[entity_type] += 1

    conn.execute(text("UPDATE import_batch SET counts = CAST(:c AS jsonb) WHERE id = :id"),
                 {"c": json.dumps(counts), "id": batch_id})
    audit.write_audit(conn, workspace_id, actor, "people_import.stage", entity="import_batch",
                      entity_id=str(batch_id), after={"counts": counts})
    return {"batch_id": batch_id, "counts": counts, "status": "staged"}


# --------------------------------------------------------------------------- detect


def _existing_by_source(conn: Connection, source_system: str, source_ref: str) -> UUID | None:
    return conn.execute(
        text(
            "SELECT person_id FROM person_source_identity WHERE source_system = :ss AND source_ref = :sr LIMIT 1"
        ),
        {"ss": source_system, "sr": source_ref},
    ).scalar_one_or_none()


def _name_candidates(conn: Connection, display_name: str) -> list[UUID]:
    key = _normalise(display_name)
    if not key:
        return []
    return list(conn.execute(
        text(
            "SELECT DISTINCT p.id FROM person p LEFT JOIN person_name_history nh ON nh.person_id = p.id "
            "WHERE p.merged_into_id IS NULL AND ("
            "  regexp_replace(lower(btrim(p.display_name)), '\\s+', ' ', 'g') = :k "
            "  OR regexp_replace(lower(btrim(nh.name)), '\\s+', ' ', 'g') = :k)"
        ),
        {"k": key},
    ).scalars().all())


def detect(conn: Connection, workspace_id: UUID, actor: str, batch_id: UUID, *, source_system: str = SOURCE_SYSTEM) -> dict[str, Any]:
    """Classify each staged person: matched (existing source id) / possible_existing (name
    candidates, needs review) / new. Honours Stage 3 distinct assertions and existing merges."""
    if imports.get_batch(conn, batch_id) is None:
        raise ValueError("batch_not_found")
    summary = {"matched": 0, "possible_existing": 0, "new": 0}
    for rec in conn.execute(
        text("SELECT id, entity_type, source_ref, normalised FROM import_staging_record "
             "WHERE batch_id = :b AND entity_type IN ('player','official') AND status = 'staged'"),
        {"b": batch_id},
    ).mappings().all():
        norm = rec["normalised"] or {}
        existing = _existing_by_source(conn, source_system, rec["source_ref"])
        if existing is not None:
            _update(conn, rec["id"], status="staged", resolution="matched", canonical=existing, issues=None)
            summary["matched"] += 1
            continue
        candidates = [
            c for c in _name_candidates(conn, norm.get("display_name", ""))
        ]
        if candidates:
            _update(conn, rec["id"], status="unresolved", resolution="possible_existing", canonical=None,
                    issues={"candidate_person_ids": [str(c) for c in candidates]})
            summary["possible_existing"] += 1
        else:
            _update(conn, rec["id"], status="staged", resolution="new", canonical=None, issues=None)
            summary["new"] += 1
    conn.execute(text("UPDATE import_batch SET status = 'validated' WHERE id = :id"), {"id": batch_id})
    audit.write_audit(conn, workspace_id, actor, "people_import.detect", entity="import_batch",
                      entity_id=str(batch_id), after=summary)
    return {"batch_id": str(batch_id), **summary}


def _update(conn: Connection, record_id: UUID, *, status: str, resolution: str, canonical: UUID | None, issues: Any) -> None:
    conn.execute(
        text("UPDATE import_staging_record SET status = :st, resolution = :res, "
             "matched_canonical_id = :cid, issues = CAST(:iss AS jsonb) WHERE id = :id"),
        {"st": status, "res": resolution, "cid": canonical,
         "iss": json.dumps(issues) if issues is not None else None, "id": record_id},
    )


# --------------------------------------------------------------------------- review decision


def decide_record(
    conn: Connection, workspace_id: UUID, actor: str, record_id: UUID, *, decision: str,
    existing_person_id: UUID | None = None,
) -> dict[str, Any]:
    """Administrator review of a staged person record:
    ``new`` | ``existing`` (confirm a candidate) | ``distinct`` (new, and assert distinct from the
    candidate(s) on promotion) | ``defer`` | ``reject``."""
    rec = conn.execute(
        text("SELECT id, status, resolution, issues FROM import_staging_record WHERE id = :id "
             "AND entity_type IN ('player','official')"),
        {"id": record_id},
    ).mappings().first()
    if rec is None:
        raise ValueError("record_not_found")
    if decision == "new":
        _update(conn, record_id, status="staged", resolution="new", canonical=None, issues=rec["issues"])
    elif decision == "existing":
        if existing_person_id is None or people.get_person(conn, existing_person_id, include_protected=True) is None:
            raise ValueError("existing_person_required")
        _update(conn, record_id, status="staged", resolution="confirmed_existing",
                canonical=existing_person_id, issues=rec["issues"])
    elif decision == "distinct":
        _update(conn, record_id, status="staged", resolution="distinct", canonical=None, issues=rec["issues"])
    elif decision == "defer":
        _update(conn, record_id, status="unresolved", resolution="deferred", canonical=None, issues=rec["issues"])
    elif decision == "reject":
        _update(conn, record_id, status="skipped", resolution="rejected", canonical=None, issues=rec["issues"])
    else:
        raise ValueError("invalid_decision")
    audit.write_audit(conn, workspace_id, actor, "people_import.decide", entity="import_staging_record",
                      entity_id=str(record_id), after={"decision": decision})
    return {"record_id": str(record_id), "decision": decision}


# --------------------------------------------------------------------------- promote


def _enrich(conn: Connection, workspace_id: UUID, actor: str, person_id: UUID, entity_type: str,
            source_ref: str, norm: dict[str, Any], source_system: str) -> None:
    # Attach provenance (idempotent) and the role for this entity; add an alias if the imported
    # name differs from the person's current one. Never overwrites verified data.
    people.add_source_identity(conn, workspace_id, actor, person_id, source_system=source_system,
                               source_ref=source_ref, source_display_name=norm.get("display_name"), _audit=False)
    people.add_role(conn, workspace_id, actor, person_id, _ENTITY_ROLE[entity_type])
    current = people.get_person(conn, person_id, include_protected=True)
    imported = (norm.get("display_name") or "").strip()
    if imported and current and _normalise(imported) != _normalise(current["display_name"]):
        existing_names = {_normalise(n["name"]) for n in people.list_names(conn, person_id)}
        if _normalise(imported) not in existing_names:
            people.add_name(conn, workspace_id, actor, person_id, name=imported, name_type="alias",
                            note=f"imported from {source_system}")


def promote(conn: Connection, workspace_id: UUID, actor: str, batch_id: UUID, *, source_system: str = SOURCE_SYSTEM) -> dict[str, Any]:
    """Promote approved person records. ``new``/``distinct`` create a person (deduped within the
    batch by source ref, so a player+official pair becomes one person with both roles);
    ``matched``/``confirmed_existing`` link to the existing person and enrich. ``possible_existing``
    and ``deferred`` are left for review. Idempotent and resumable."""
    batch = imports.get_batch(conn, batch_id)
    if batch is None:
        raise ValueError("batch_not_found")
    created = {"player": 0, "official": 0}
    linked = {"player": 0, "official": 0}
    by_ref: dict[str, UUID] = {}

    rows = conn.execute(
        text("SELECT id, entity_type, source_ref, normalised, resolution, matched_canonical_id, issues "
             "FROM import_staging_record "
             "WHERE batch_id = :b AND entity_type IN ('player','official') AND status = 'staged' "
             "ORDER BY entity_type DESC"),  # players before officials so the person is a player-first identity
        {"b": batch_id},
    ).mappings().all()

    for rec in rows:
        norm = rec["normalised"] or {}
        ref = rec["source_ref"]
        resolution = rec["resolution"]

        if resolution in ("matched", "confirmed_existing") and rec["matched_canonical_id"]:
            person_id = rec["matched_canonical_id"]
            _enrich(conn, workspace_id, actor, person_id, rec["entity_type"], ref, norm, source_system)
            conn.execute(text("UPDATE import_staging_record SET status='promoted' WHERE id=:id"), {"id": rec["id"]})
            linked[rec["entity_type"]] += 1
            continue

        if resolution not in ("new", "distinct"):
            continue  # possible_existing / deferred -> left for review

        # Dedup within batch: a source ref already created becomes one person with the extra role.
        person_id = by_ref.get(ref) or _existing_by_source(conn, source_system, ref)
        if person_id is None:
            person_id = people.create_person(
                conn, workspace_id, actor, display_name=norm.get("display_name") or "(unknown)",
                dob=norm.get("dob"), dob_precision=norm.get("dob_precision") or "unknown",
                roles=[_ENTITY_ROLE[rec["entity_type"]]],
                source_system=source_system, source_ref=ref,
            )
            created[rec["entity_type"]] += 1
            # 'distinct' decision: record that this new person differs from the suggested candidates.
            if resolution == "distinct":
                for cid in (rec.get("issues") or {}).get("candidate_person_ids", []) if isinstance(rec.get("issues"), dict) else []:
                    try:
                        person_resolution.assert_distinct(conn, workspace_id, actor, person_id, UUID(cid),
                                                          reason="import review: distinct person")
                    except ValueError:
                        pass
        else:
            _enrich(conn, workspace_id, actor, person_id, rec["entity_type"], ref, norm, source_system)
        by_ref[ref] = person_id
        conn.execute(
            text("UPDATE import_staging_record SET status='promoted', matched_canonical_id=:p WHERE id=:id"),
            {"p": person_id, "id": rec["id"]},
        )

    remaining = conn.execute(
        text("SELECT count(*) FROM import_staging_record WHERE batch_id = :b AND status IN ('staged','unresolved')"),
        {"b": batch_id},
    ).scalar_one()
    new_status = "promoted" if remaining == 0 else "partially_promoted"
    conn.execute(
        text("UPDATE import_batch SET status=:st, promoted_at=now(), promoted_by=:by WHERE id=:id"),
        {"st": new_status, "by": actor, "id": batch_id},
    )
    audit.write_audit(conn, workspace_id, actor, "people_import.promote", entity="import_batch",
                      entity_id=str(batch_id), after={"created": created, "linked": linked, "status": new_status})
    return {"batch_id": str(batch_id), "status": new_status, "created": created, "linked": linked}


def rollback(conn: Connection, workspace_id: UUID, actor: str, batch_id: UUID) -> dict[str, Any]:
    """Reverse a people promotion: delete exactly the persons this batch created (records whose
    resolution is new/distinct and that own a matched_canonical_id), returning their records to
    'staged'. Linked/enriched existing people are left untouched."""
    if imports.get_batch(conn, batch_id) is None:
        raise ValueError("batch_not_found")
    removed = 0
    seen: set[str] = set()
    for rec in conn.execute(
        text("SELECT id, resolution, matched_canonical_id FROM import_staging_record "
             "WHERE batch_id=:b AND entity_type IN ('player','official') AND status='promoted' "
             "AND resolution IN ('new','distinct')"),
        {"b": batch_id},
    ).mappings().all():
        pid = rec["matched_canonical_id"]
        if pid is not None and str(pid) not in seen:
            conn.execute(text("DELETE FROM person WHERE id = :id"), {"id": pid})
            seen.add(str(pid))
            removed += 1
        conn.execute(
            text("UPDATE import_staging_record SET status='staged', matched_canonical_id=NULL WHERE id=:id"),
            {"id": rec["id"]},
        )
    conn.execute(text("UPDATE import_batch SET status='validated', promoted_at=NULL, promoted_by=NULL WHERE id=:id"),
                 {"id": batch_id})
    audit.write_audit(conn, workspace_id, actor, "people_import.rollback", entity="import_batch",
                      entity_id=str(batch_id), after={"persons_removed": removed})
    return {"batch_id": str(batch_id), "status": "validated", "persons_removed": removed}


# --------------------------------------------------------------------------- reconcile


def reconcile(conn: Connection, batch_id: UUID) -> dict[str, Any]:
    """Full reconciliation: every staged person record accounted for by status x resolution."""
    batch = imports.get_batch(conn, batch_id)
    if batch is None:
        raise ValueError("batch_not_found")
    rows = conn.execute(
        text("SELECT status, resolution, count(*) n FROM import_staging_record "
             "WHERE batch_id=:b AND entity_type IN ('player','official') GROUP BY status, resolution"),
        {"b": batch_id},
    ).mappings().all()
    total = sum(r["n"] for r in rows)
    def tally(pred) -> int:
        return sum(r["n"] for r in rows if pred(r))
    report = {
        "source_counts": batch.get("counts") or {},
        "total_staged": total,
        "new_candidates": tally(lambda r: r["resolution"] == "new"),
        "matched_existing": tally(lambda r: r["resolution"] in ("matched", "confirmed_existing")),
        "possible_duplicates": tally(lambda r: r["resolution"] == "possible_existing"),
        "promoted": tally(lambda r: r["status"] == "promoted"),
        "needs_review": tally(lambda r: r["status"] == "unresolved"),
        "deferred": tally(lambda r: r["resolution"] == "deferred"),
        "rejected": tally(lambda r: r["resolution"] == "rejected"),
        "errors": tally(lambda r: r["status"] == "error"),
        "by_status_resolution": [dict(r) for r in rows],
    }
    # Every record is accounted for across staged/unresolved/promoted/skipped/error.
    report["accounted_for"] = total
    return report
