"""Cricket Statz structural import (Phase 4, Stage 6).

A staging-first pipeline: source rows are parsed verbatim into ``import_staging_record`` under
an ``import_batch`` (source IDs + provenance preserved), validated for referential integrity,
previewed, and only **promoted** into the canonical Phase 1-5 tables on explicit administrator
approval. Promotion is **idempotent** (keyed on source_ref — re-import never duplicates),
**reversible** (``rollback_batch`` removes exactly the canonical rows this batch created), and
**audited**. Nothing is silently discarded.

Scope (evidence-verified structural mappings only — D32/D35, deliverable 16a):

* ``clubs`` → organisation (kind=club), ``teams`` → team (+ organisation link), ``venues`` →
  venue, ``divisions`` → grade (A/B/C Grade confident; others left **unresolved**) under a
  single import competition container.
* ``matches`` are staged **structurally only** and are **not promoted** — there is no canonical
  match table yet (scorecards are Phase 8). Their finals classification is derived only as a
  low-confidence hint and kept **unresolved**; Result codes 3/4/8/9 stay **unresolved**.

No batting/bowling/fielding/scorecards. No auto-merge by name (identity resolution stays an
administrator decision). Unknown ≠ zero throughout (sentinels map to unknown).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain import audit, competitions, organisations, teams, venues

SOURCE_SYSTEM = "cricket_statz"
_IMPORT_COMP_REF = "cricket_statz:import"

# Confirmed by cross-reference (16a.14 / 16a.9).
MATCHTYPE_LABELS = {1: "1 innings per side", 2: "2 innings per side", 3: "T20"}
# Only 0/1/2 are evidence-confirmed; 3/4/8/9 must stay unresolved (never guessed).
RESULT_LABELS = {0: "unknown", 1: "home_win", 2: "away_win"}
# Grade names safe to promote directly; anything else is left unresolved for admin review.
CONFIDENT_GRADES = {"a grade", "b grade", "c grade"}


# --------------------------------------------------------------------------- helpers


def _sha256(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def _round_classification_hint(round_label: str) -> str:
    """A *low-confidence* hint only — never authoritative (user rule, D32). Classification is
    always stored as unresolved for human confirmation."""
    r = (round_label or "").strip().lower()
    if r in ("gf", "gf1", "gf2", "grand final"):
        return "grand_final?"
    if r in ("sf", "semi", "semi final", "semifinal"):
        return "final?"
    if r.isdigit():
        return "home_away?"
    return "unknown"


def get_batch(conn: Connection, batch_id: UUID) -> dict[str, Any] | None:
    r = conn.execute(
        text(
            "SELECT id, source_system, source_filename, source_sha256, status, counts, notes, "
            "created_by, created_at, promoted_at, promoted_by FROM import_batch WHERE id = :id"
        ),
        {"id": batch_id},
    ).mappings().first()
    return dict(r) if r else None


def list_batches(conn: Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(
            "SELECT id, source_system, source_filename, status, counts, created_at, promoted_at "
            "FROM import_batch ORDER BY created_at DESC"
        )
    ).mappings().all()
    return [dict(r) for r in rows]


def list_records(
    conn: Connection, batch_id: UUID, *, entity_type: str | None = None, status: str | None = None
) -> list[dict[str, Any]]:
    sql = (
        "SELECT id, entity_type, source_ref, raw, normalised, status, resolution, "
        "matched_canonical_id, issues FROM import_staging_record WHERE batch_id = :b"
    )
    params: dict[str, Any] = {"b": batch_id}
    if entity_type:
        sql += " AND entity_type = :et"
        params["et"] = entity_type
    if status:
        sql += " AND status = :st"
        params["st"] = status
    sql += " ORDER BY entity_type, source_ref"
    return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]


def _staged(conn: Connection, batch_id: UUID, entity_type: str) -> list[dict[str, Any]]:
    return list_records(conn, batch_id, entity_type=entity_type)


def _insert_record(
    conn: Connection, wid: UUID, batch_id: UUID, entity_type: str, source_ref: str,
    raw: Any, normalised: dict[str, Any], *, status: str = "staged",
    resolution: str | None = None, issues: list[str] | None = None,
) -> None:
    # ON CONFLICT DO NOTHING: duplicate source rows (e.g. a mirrored grand final) are collapsed
    # on (batch, entity_type, source_ref) rather than erroring — nothing is discarded silently
    # beyond an exact in-batch duplicate of the same source id.
    conn.execute(
        text(
            "INSERT INTO import_staging_record"
            "(workspace_id, batch_id, entity_type, source_ref, raw, normalised, status, resolution, issues) "
            "VALUES (:w, :b, :et, :sr, CAST(:raw AS jsonb), CAST(:norm AS jsonb), :st, :res, CAST(:iss AS jsonb)) "
            "ON CONFLICT ON CONSTRAINT uq_staging_record DO NOTHING"
        ),
        {
            "w": wid, "b": batch_id, "et": entity_type, "sr": str(source_ref),
            "raw": json.dumps(raw, default=str), "norm": json.dumps(normalised, default=str),
            "st": status, "res": resolution,
            "iss": json.dumps(issues) if issues else None,
        },
    )


# --------------------------------------------------------------------------- stage


def parse_and_stage(
    conn: Connection, workspace_id: UUID, actor: str, *, payload: dict[str, Any], filename: str | None = None
) -> dict[str, Any]:
    """Validate the source payload and stage every row verbatim. No canonical write occurs."""
    if not isinstance(payload, dict):
        raise ValueError("invalid_payload")  # noqa: TRY004 — uniform ValueError→422 handling
    known = ("clubs", "teams", "venues", "divisions", "matches")
    if not any(k in payload and payload[k] for k in known):
        raise ValueError("no_importable_collections")

    batch_id = conn.execute(
        text(
            "INSERT INTO import_batch(workspace_id, source_system, source_filename, source_sha256, created_by) "
            "VALUES (:w, :ss, :fn, :sha, :actor) RETURNING id"
        ),
        {"w": workspace_id, "ss": SOURCE_SYSTEM, "fn": filename, "sha": _sha256(payload), "actor": actor},
    ).scalar_one()

    counts: dict[str, int] = {}

    for row in payload.get("clubs") or []:
        ref = row.get("ClubID")
        if ref is None:
            continue
        _insert_record(conn, workspace_id, batch_id, "club", ref, row,
                       {"name": row.get("Name"), "kind": "club"}, resolution="new")
    counts["club"] = len(payload.get("clubs") or [])

    for row in payload.get("venues") or []:
        ref = row.get("GroundID")
        if ref is None:
            continue
        unknown = row.get("Name") == "?"
        _insert_record(conn, workspace_id, batch_id, "venue", ref, row,
                       {"name": None if unknown else row.get("Name"), "unknown_name": unknown},
                       resolution="new")
    counts["venue"] = len(payload.get("venues") or [])

    for row in payload.get("divisions") or []:
        ref = row.get("GradeID")
        if ref is None:
            continue
        name = row.get("Name") or ""
        confident = name.strip().lower() in CONFIDENT_GRADES
        _insert_record(
            conn, workspace_id, batch_id, "division", ref, row,
            {"name": name, "confident": confident},
            status="staged" if confident else "unresolved",
            resolution="new" if confident else "unresolved",
            issues=None if confident else ["ambiguous_grade: preserve original; admin must resolve"],
        )
    counts["division"] = len(payload.get("divisions") or [])

    for row in payload.get("teams") or []:
        ref = row.get("TeamID")
        if ref is None:
            continue
        _insert_record(conn, workspace_id, batch_id, "team", ref, row,
                       {"name": row.get("Name"), "club_source_ref": _s(row.get("ClubID"))},
                       resolution="new")
    counts["team"] = len(payload.get("teams") or [])

    for row in payload.get("matches") or []:
        ref = row.get("MatchID")
        if ref is None:
            continue
        result = row.get("Result")
        result_known = result in RESULT_LABELS
        issues: list[str] = []
        if not result_known:
            issues.append(f"result_unresolved: code {result} not evidence-verified")
        # Classification is ALWAYS 'unclassified'/unverified at import — the round label is a
        # non-authoritative hint only, and a missing classification is never Home & Away.
        issues.append("classification_unresolved: round is a hint only; admin must classify")
        norm = {
            "date_played": row.get("DatePlayed"),
            "home_team_source_ref": _s(row.get("HomeTeam")),
            "away_team_source_ref": _s(row.get("AwayTeam")),
            "grade_source_ref": _s(row.get("Grade")),
            "venue_source_ref": _s(row.get("Ground")),
            "round": row.get("round"),  # verbatim, never used to classify
            "matchtype": row.get("matchtype"),
            "matchtype_label": MATCHTYPE_LABELS.get(row.get("matchtype")),
            "result": result,
            "result_label": RESULT_LABELS.get(result) if result_known else None,
            "result_status": "known" if result_known else "unresolved",
            # Structured classification candidate (revised model): explicit, unverified.
            "classification": "unclassified",
            "finals_stage": None,
            "classification_verified": False,
            "classification_candidate_hint": _round_classification_hint(row.get("round") or ""),
            "classification_status": "unresolved",
            "home_points": row.get("homebpoints"),
            "away_points": row.get("awaybpoints"),
        }
        # Matches are staged structurally only; never promoted in Stage 6 (no canonical match table).
        _insert_record(conn, workspace_id, batch_id, "match", ref, row, norm,
                       status="staged", resolution="staged_only", issues=issues)
    counts["match"] = len(payload.get("matches") or [])

    conn.execute(
        text("UPDATE import_batch SET counts = CAST(:c AS jsonb) WHERE id = :id"),
        {"c": json.dumps(counts), "id": batch_id},
    )
    audit.write_audit(conn, workspace_id, actor, "import.stage", entity="import_batch",
                      entity_id=str(batch_id), after={"counts": counts, "filename": filename})
    return {"batch_id": batch_id, "counts": counts, "status": "staged"}


def _s(v: Any) -> str | None:
    return None if v is None else str(v)


# --------------------------------------------------------------------------- validate


def validate_batch(conn: Connection, workspace_id: UUID, actor: str, batch_id: UUID) -> dict[str, Any]:
    """Referential-integrity checks across staged rows; records (never drops) any broken refs."""
    if get_batch(conn, batch_id) is None:
        raise ValueError("batch_not_found")
    club_refs = {r["source_ref"] for r in _staged(conn, batch_id, "club")}
    team_refs = {r["source_ref"] for r in _staged(conn, batch_id, "team")}
    venue_refs = {r["source_ref"] for r in _staged(conn, batch_id, "venue")}
    div_refs = {r["source_ref"] for r in _staged(conn, batch_id, "division")}

    problems = 0
    for rec in _staged(conn, batch_id, "team"):
        norm = rec["normalised"] or {}
        if norm.get("club_source_ref") and norm["club_source_ref"] not in club_refs:
            problems += _flag(conn, rec["id"], "club_ref_unresolved")
    for rec in list_records(conn, batch_id, entity_type="match"):
        norm = rec["normalised"] or {}
        for key, refs, label in (
            ("home_team_source_ref", team_refs, "home_team_ref_unresolved"),
            ("away_team_source_ref", team_refs, "away_team_ref_unresolved"),
            ("grade_source_ref", div_refs, "grade_ref_unresolved"),
            ("venue_source_ref", venue_refs, "venue_ref_unresolved"),
        ):
            if norm.get(key) and norm[key] not in refs:
                problems += _flag(conn, rec["id"], label)

    conn.execute(text("UPDATE import_batch SET status = 'validated' WHERE id = :id"), {"id": batch_id})
    audit.write_audit(conn, workspace_id, actor, "import.validate", entity="import_batch",
                      entity_id=str(batch_id), after={"ref_problems": problems})
    return {"batch_id": batch_id, "status": "validated", "ref_problems": problems}


def _flag(conn: Connection, record_id: UUID, issue: str) -> int:
    # Append the issue as a one-element JSON array (avoids a `::text` cast adjacent to a bind
    # param, which SQLAlchemy's text() mis-parses).
    conn.execute(
        text(
            "UPDATE import_staging_record "
            "SET issues = coalesce(issues, '[]'::jsonb) || CAST(:iss AS jsonb) WHERE id = :id"
        ),
        {"iss": json.dumps([issue]), "id": record_id},
    )
    return 1


# --------------------------------------------------------------------------- preview


def preview_batch(conn: Connection, batch_id: UUID) -> dict[str, Any]:
    """Read-only summary of what promotion would do; promotes nothing."""
    if get_batch(conn, batch_id) is None:
        raise ValueError("batch_not_found")
    rows = conn.execute(
        text(
            "SELECT entity_type, status, count(*) n FROM import_staging_record "
            "WHERE batch_id = :b GROUP BY entity_type, status ORDER BY entity_type, status"
        ),
        {"b": batch_id},
    ).mappings().all()
    summary: dict[str, dict[str, int]] = {}
    for r in rows:
        summary.setdefault(r["entity_type"], {})[r["status"]] = r["n"]
    promotable = sum(
        v.get("staged", 0) for k, v in summary.items() if k in ("club", "venue", "team", "division")
    )
    unresolved = sum(v.get("unresolved", 0) for v in summary.values())
    return {
        "batch_id": str(batch_id),
        "by_entity": summary,
        "promotable_now": promotable,
        "unresolved": unresolved,
        "matches_staged_only": summary.get("match", {}).get("staged", 0),
    }


# --------------------------------------------------------------------------- promote


def _find_canonical_by_source(conn: Connection, table: str, fk_col: str, source_ref: str) -> UUID | None:
    """Existing canonical id for a CS source_ref via the entity's source-identity table."""
    return conn.execute(
        text(
            f"SELECT {fk_col} FROM {table} WHERE source_system = :ss AND source_ref = :sr LIMIT 1"
        ),
        {"ss": SOURCE_SYSTEM, "sr": source_ref},
    ).scalar_one_or_none()


def _get_or_create_import_competition(conn: Connection, workspace_id: UUID, actor: str) -> UUID:
    existing = _find_canonical_by_source(conn, "competition_source_identity", "competition_id", _IMPORT_COMP_REF)
    if existing is not None:
        return existing
    return competitions.create_competition(
        conn, workspace_id, actor, name="Cricket Statz Import",
        notes="Container for grades imported from Cricket Statz divisions.",
        source_system=SOURCE_SYSTEM, source_ref=_IMPORT_COMP_REF,
    )


def _set_record(conn: Connection, record_id: UUID, *, status: str, resolution: str, canonical_id: UUID | None) -> None:
    conn.execute(
        text(
            "UPDATE import_staging_record SET status = :st, resolution = :res, matched_canonical_id = :cid WHERE id = :id"
        ),
        {"st": status, "res": resolution, "cid": canonical_id, "id": record_id},
    )


def promote_batch(conn: Connection, workspace_id: UUID, actor: str, batch_id: UUID) -> dict[str, Any]:
    """Promote staged, promotable rows into canonical tables (explicit admin approval).

    Idempotent: a row whose source_ref already exists canonically is *matched*, never duplicated;
    names are never auto-merged. Unresolved divisions and all matches are left in staging.
    """
    batch = get_batch(conn, batch_id)
    if batch is None:
        raise ValueError("batch_not_found")
    if batch["status"] in ("cancelled", "promoted"):
        raise ValueError(f"batch_{batch['status']}")

    created = {"club": 0, "venue": 0, "team": 0, "division": 0}
    matched = {"club": 0, "venue": 0, "team": 0, "division": 0}

    def promotable(entity_type: str) -> list[dict[str, Any]]:
        # Only 'staged' rows promote: 'unresolved' (ambiguous grades) and already-'promoted'
        # rows are skipped, so promotion is safe to re-run and never touches ambiguous data.
        return list_records(conn, batch_id, entity_type=entity_type, status="staged")

    # clubs -> organisation
    for rec in promotable("club"):
        norm = rec["normalised"] or {}
        existing = _find_canonical_by_source(conn, "organisation_source_identity", "organisation_id", rec["source_ref"])
        if existing is not None:
            _set_record(conn, rec["id"], status="promoted", resolution="matched", canonical_id=existing)
            matched["club"] += 1
            continue
        oid = organisations.create_organisation(
            conn, workspace_id, actor, name=norm.get("name") or "(unnamed club)", kind="club",
            source_system=SOURCE_SYSTEM, source_ref=rec["source_ref"],
        )
        _set_record(conn, rec["id"], status="promoted", resolution="new", canonical_id=oid)
        created["club"] += 1

    # venues
    for rec in promotable("venue"):
        norm = rec["normalised"] or {}
        existing = _find_canonical_by_source(conn, "venue_source_identity", "venue_id", rec["source_ref"])
        if existing is not None:
            _set_record(conn, rec["id"], status="promoted", resolution="matched", canonical_id=existing)
            matched["venue"] += 1
            continue
        vid = venues.create_venue(
            conn, workspace_id, actor, name=norm.get("name") or "Unknown venue",
            source_system=SOURCE_SYSTEM, source_ref=rec["source_ref"],
        )
        _set_record(conn, rec["id"], status="promoted", resolution="new", canonical_id=vid)
        created["venue"] += 1

    # divisions -> grade (confident only; ambiguous stay unresolved and are not in 'staged')
    comp_id: UUID | None = None
    confident_divs = promotable("division")
    if confident_divs:
        comp_id = _get_or_create_import_competition(conn, workspace_id, actor)
    for rec in confident_divs:
        norm = rec["normalised"] or {}
        existing = conn.execute(
            text("SELECT id FROM grade WHERE competition_id = :c AND source_ref = :sr"),
            {"c": comp_id, "sr": rec["source_ref"]},
        ).scalar_one_or_none()
        if existing is not None:
            _set_record(conn, rec["id"], status="promoted", resolution="matched", canonical_id=existing)
            matched["division"] += 1
            continue
        gid = competitions.create_grade(
            conn, workspace_id, actor, comp_id, name=norm.get("name") or "(grade)",
            source_system=SOURCE_SYSTEM, source_ref=rec["source_ref"],
        )
        _set_record(conn, rec["id"], status="promoted", resolution="new", canonical_id=gid)
        created["division"] += 1

    # teams -> team (needs its club promoted/matched first)
    for rec in promotable("team"):
        norm = rec["normalised"] or {}
        existing = _find_canonical_by_source(conn, "team_source_identity", "team_id", rec["source_ref"])
        if existing is not None:
            _set_record(conn, rec["id"], status="promoted", resolution="matched", canonical_id=existing)
            matched["team"] += 1
            continue
        club_ref = norm.get("club_source_ref")
        org_id = _find_canonical_by_source(conn, "organisation_source_identity", "organisation_id", club_ref) if club_ref else None
        if org_id is None:
            _flag(conn, rec["id"], "club_not_promoted: team left staged")
            continue
        tid = teams.create_team(
            conn, workspace_id, actor, organisation_id=org_id, name=norm.get("name") or "(team)",
            source_system=SOURCE_SYSTEM, source_ref=rec["source_ref"],
        )
        _set_record(conn, rec["id"], status="promoted", resolution="new", canonical_id=tid)
        created["team"] += 1

    # matches: structural staging only — never promoted in Stage 6 (Phase 8 owns scorecards).
    remaining_unresolved = conn.execute(
        text("SELECT count(*) FROM import_staging_record WHERE batch_id = :b AND status IN ('staged','unresolved')"),
        {"b": batch_id},
    ).scalar_one()
    new_status = "promoted" if remaining_unresolved == 0 else "partially_promoted"
    conn.execute(
        text("UPDATE import_batch SET status = :st, promoted_at = now(), promoted_by = :by WHERE id = :id"),
        {"st": new_status, "by": actor, "id": batch_id},
    )
    audit.write_audit(conn, workspace_id, actor, "import.promote", entity="import_batch",
                      entity_id=str(batch_id), after={"created": created, "matched": matched, "status": new_status})
    return {"batch_id": str(batch_id), "status": new_status, "created": created, "matched": matched}


# --------------------------------------------------------------------------- cancel / rollback


def cancel_batch(conn: Connection, workspace_id: UUID, actor: str, batch_id: UUID) -> dict[str, Any]:
    """Cancel a batch that has not promoted anything into canonical tables."""
    batch = get_batch(conn, batch_id)
    if batch is None:
        raise ValueError("batch_not_found")
    promoted = conn.execute(
        text("SELECT count(*) FROM import_staging_record WHERE batch_id = :b AND resolution = 'new' AND status = 'promoted'"),
        {"b": batch_id},
    ).scalar_one()
    if promoted:
        raise ValueError("batch_has_promoted_rows_use_rollback")
    conn.execute(text("UPDATE import_batch SET status = 'cancelled' WHERE id = :id"), {"id": batch_id})
    audit.write_audit(conn, workspace_id, actor, "import.cancel", entity="import_batch", entity_id=str(batch_id))
    return {"batch_id": str(batch_id), "status": "cancelled"}


def rollback_batch(conn: Connection, workspace_id: UUID, actor: str, batch_id: UUID) -> dict[str, Any]:
    """Reverse a promotion: delete exactly the canonical rows this batch created (resolution='new'),
    in dependency order, and return the staging records to 'staged'. Matched (pre-existing) rows are
    left untouched. Freshly imported rows have no other dependents, so deletion is safe and complete."""
    batch = get_batch(conn, batch_id)
    if batch is None:
        raise ValueError("batch_not_found")
    removed = {"team": 0, "division": 0, "venue": 0, "club": 0}
    order = [("team", "team"), ("division", "grade"), ("venue", "venue"), ("club", "organisation")]
    for entity_type, table in order:
        for rec in list_records(conn, batch_id, entity_type=entity_type, status="promoted"):
            if rec["resolution"] != "new" or rec["matched_canonical_id"] is None:
                continue
            conn.execute(text(f"DELETE FROM {table} WHERE id = :id"), {"id": rec["matched_canonical_id"]})
            _set_record(conn, rec["id"], status="staged", resolution="new", canonical_id=None)
            removed[entity_type] += 1
    conn.execute(
        text("UPDATE import_batch SET status = 'validated', promoted_at = NULL, promoted_by = NULL WHERE id = :id"),
        {"id": batch_id},
    )
    audit.write_audit(conn, workspace_id, actor, "import.rollback", entity="import_batch",
                      entity_id=str(batch_id), after={"removed": removed})
    return {"batch_id": str(batch_id), "status": "validated", "removed": removed}
