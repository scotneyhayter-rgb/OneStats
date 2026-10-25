"""Generic import pipeline — Phase 8, Stage 8.3.

Turns any adapter's :class:`CanonicalDataset` into staged ``import_staging_record`` rows (the same
substrate the CricketStatz importer uses) and drives the shared, source-agnostic ``promote_batch``.
One pipeline for every source: an adapter maps a file to the CCDM, this stages it, and the existing
promoter (now source-aware) creates/matches the canonical rows — idempotent, reversible, audited.

Structural + match entities are staged here; the CricketStatz scorecard body keeps its proven stager
until its migration onto this one (next sub-stage), so nothing regresses. Imported matches enter the
normal draft/approval flow — importing never approves and never feeds official statistics by itself.
"""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain import audit, imports
from onestats.domain.importing.model import CanonicalDataset, CanonicalMatch


def _toss_code(toss_won_by: str | None) -> int | None:
    """CCDM home/away toss → the home/away code promote_batch understands (1 home, 2 away)."""
    return 1 if toss_won_by == "home" else 2 if toss_won_by == "away" else None


def _match_norm(m: CanonicalMatch) -> dict[str, Any]:
    """CCDM match → the ``normalised`` payload promote_batch reads (neutral source refs; unknowns
    stay None; captains/keepers/toss preserved; round is a label only, never a classification)."""
    return {
        "home_team_source_ref": m.home_team_ref,
        "away_team_source_ref": m.away_team_ref,
        "grade_source_ref": m.grade_ref,
        "venue_source_ref": m.venue_ref,
        "date_played": m.match_date.isoformat() if m.match_date else None,
        "round": m.round,
        "matchtype_label": m.match_format,
        "result": m.result_code,
        "result_label": m.result_type,
        "result_status": m.result_status,
        "home_captain_source_ref": m.home_captain_ref,
        "home_keeper_source_ref": m.home_keeper_ref,
        "home_keeper2_source_ref": m.home_keeper2_ref,
        "away_captain_source_ref": m.away_captain_ref,
        "away_keeper_source_ref": m.away_keeper_ref,
        "away_keeper2_source_ref": m.away_keeper2_ref,
        "toss_won_by_code": _toss_code(m.toss_won_by),
    }


def stage_dataset(
    conn: Connection, workspace_id: UUID, actor: str, dataset: CanonicalDataset, *, filename: str | None = None,
) -> dict[str, Any]:
    """Stage a Canonical dataset's structural + match rows verbatim under a new import batch. No
    canonical write occurs; promotion is a separate, explicit step. Returns the batch id and counts."""
    problems = dataset.validate_provenance()
    if problems:
        raise ValueError(f"dataset_provenance_invalid: {problems[0]}")
    source_system = dataset.provenance.source_system
    sha = dataset.provenance.sha256 or imports._sha256(dataset.counts())
    batch_id = conn.execute(
        text("INSERT INTO import_batch(workspace_id, source_system, source_filename, source_sha256, created_by) "
             "VALUES (:w, :ss, :fn, :sha, :actor) RETURNING id"),
        {"w": workspace_id, "ss": source_system, "fn": filename or dataset.provenance.filename,
         "sha": sha, "actor": actor},
    ).scalar_one()

    for c in dataset.clubs:
        imports._insert_record(conn, workspace_id, batch_id, "club", c.source_ref, _raw(c),
                               {"name": c.name, "kind": "club"}, resolution="new")
    for v in dataset.venues:
        imports._insert_record(conn, workspace_id, batch_id, "venue", v.source_ref, _raw(v),
                               {"name": v.name, "unknown_name": v.name is None}, resolution="new")
    for g in dataset.grades:
        # a named grade from a structured source is promotable; an unnamed one stays unresolved
        named = bool((g.name or "").strip())
        imports._insert_record(conn, workspace_id, batch_id, "division", g.source_ref, _raw(g),
                               {"name": g.name, "confident": named},
                               status="staged" if named else "unresolved",
                               resolution="new" if named else "unresolved",
                               issues=None if named else ["ambiguous_grade: preserve original; admin must resolve"])
    for t in dataset.teams:
        imports._insert_record(conn, workspace_id, batch_id, "team", t.source_ref, _raw(t),
                               {"name": t.name, "club_source_ref": t.club_ref}, resolution="new")
    for m in dataset.matches:
        imports._insert_record(conn, workspace_id, batch_id, "match", m.source_ref, _raw(m),
                               _match_norm(m), resolution="new")

    counts = {k: v for k, v in dataset.counts().items() if k in ("clubs", "teams", "venues", "grades", "matches")}
    conn.execute(text("UPDATE import_batch SET counts = CAST(:c AS jsonb) WHERE id = :id"),
                 {"c": json.dumps(counts), "id": batch_id})
    audit.write_audit(conn, workspace_id, actor, "import.stage", entity="import_batch",
                      entity_id=str(batch_id), after={"counts": counts, "source_system": source_system})
    return {"batch_id": batch_id, "counts": counts, "source_system": source_system}


def import_dataset(
    conn: Connection, workspace_id: UUID, actor: str, *, dataset: CanonicalDataset,
    commit: bool = False, filename: str | None = None,
) -> dict[str, Any]:
    """Stage a dataset and, when ``commit``, promote it through the shared source-agnostic promoter.
    Non-commit is a preview (nothing persists into canonical tables). Imported matches are draft."""
    staged = stage_dataset(conn, workspace_id, actor, dataset, filename=filename)
    out: dict[str, Any] = {"batch_id": str(staged["batch_id"]), "counts": staged["counts"],
                           "source_system": staged["source_system"], "committed": commit}
    if commit:
        promoted = imports.promote_batch(conn, workspace_id, actor, staged["batch_id"])
        out["created"] = promoted["created"]
        out["matched"] = promoted["matched"]
        out["status"] = promoted["status"]
    return out


def _raw(obj: Any) -> dict[str, Any]:
    """The verbatim-ish source view kept for provenance (the Canonical fields, which themselves carry
    the source refs/names). The adapter's original rows are the ultimate source; this is sufficient to
    trace and re-derive without altering anything."""
    from dataclasses import asdict
    return {k: (v.isoformat() if hasattr(v, "isoformat") else v)
            for k, v in asdict(obj).items() if not isinstance(v, list)}
