"""AutoSync discovery (Phase 9, Stages 9.4-9.9).

Turns what a connector yields into reviewable discoveries, using the Phase 8 duplicate framework and
import pipeline — never a parallel path. New matches are classified (new / existing / possible
duplicate / additional evidence / insufficient) and queued for review, or, only in authorised mode
with the approver permission, imported (as draft) and approved. Scorecard changes are detected against
each match's stored source evidence and queued — an approved scorecard is never silently overwritten.
Coverage records what was actually searched, so an empty result is never mistaken for "verified, no
matches". Incomplete discoveries are preserved; only approved scorecards feed official statistics.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain import audit, match_sources, matches, recalc
from onestats.domain.autosync import sources
from onestats.domain.importing import dedupe, pipeline
from onestats.domain.importing.model import (
    CanonicalClub,
    CanonicalDataset,
    CanonicalMatch,
    CanonicalTeam,
    SourceProvenance,
)
from onestats.domain.importing.sync import AUTHORISED_AUTOMATIC, SYNC_MODES

# ---- coverage (9.4) -------------------------------------------------------------------------------

def record_coverage(conn: Connection, workspace_id: UUID, actor: str, *, source_id: UUID | None,
                    scope_key: str, scope: dict[str, Any] | None, status: str,
                    matches_found: int = 0, notes: str | None = None) -> dict[str, Any]:
    """Upsert a coverage record. ``status`` distinguishes searched / partial / awaiting / no_source /
    failed — a failed or empty search is NOT recorded as 'searched' with implied completeness."""
    if status not in ("searched", "partial", "awaiting", "no_source", "failed"):
        raise ValueError("invalid_coverage_status")
    row = conn.execute(
        text("SELECT id FROM discovery_coverage WHERE workspace_id = :w "
             "AND source_id IS NOT DISTINCT FROM :sid AND scope_key = :k"),
        {"w": workspace_id, "sid": source_id, "k": scope_key},
    ).scalar_one_or_none()
    if row is not None:
        conn.execute(
            text("UPDATE discovery_coverage SET status = :st, matches_found = :mf, scope = CAST(:sc AS jsonb), "
                 "searched_at = now(), notes = :nt, updated_at = now() WHERE id = :id"),
            {"st": status, "mf": matches_found, "sc": json.dumps(scope) if scope else None, "nt": notes, "id": row},
        )
        cid = row
    else:
        cid = conn.execute(
            text("INSERT INTO discovery_coverage(workspace_id, source_id, scope_key, scope, status, "
                 "matches_found, searched_at, notes) VALUES (:w, :sid, :k, CAST(:sc AS jsonb), :st, :mf, now(), :nt) "
                 "RETURNING id"),
            {"w": workspace_id, "sid": source_id, "k": scope_key, "sc": json.dumps(scope) if scope else None,
             "st": status, "mf": matches_found, "nt": notes},
        ).scalar_one()
    return dict(conn.execute(text("SELECT * FROM discovery_coverage WHERE id = :id"), {"id": cid}).mappings().one())


def list_coverage(conn: Connection, workspace_id: UUID) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(
        text("SELECT * FROM discovery_coverage WHERE workspace_id = :w ORDER BY scope_key"),
        {"w": workspace_id}).mappings().all()]


# ---- classification + serialisation ---------------------------------------------------------------

def _team_names(ds: CanonicalDataset) -> dict[str, str | None]:
    return {t.source_ref: t.name for t in ds.teams}


def _team_id_by_name(conn: Connection, workspace_id: UUID, name: str | None) -> UUID | None:
    if not name:
        return None
    return conn.execute(
        text("SELECT id FROM team WHERE workspace_id = :w AND lower(name) = lower(:n) LIMIT 1"),
        {"w": workspace_id, "n": name},
    ).scalar_one_or_none()


def classify_match(conn: Connection, workspace_id: UUID, source_system: str, m: CanonicalMatch,
                   names: dict[str, str | None]) -> dict[str, Any]:
    """Classify a discovered match against what OneStats already holds. Never merges — returns a
    classification, a candidate match id where one is found, confidence and reasons."""
    home_name, away_name = names.get(m.home_team_ref), names.get(m.away_team_ref)
    if not m.match_date or not home_name or not away_name:
        return {"classification": "insufficient", "match_id": None, "confidence": None,
                "reasons": ["missing date or team"]}
    home_id = _team_id_by_name(conn, workspace_id, home_name)
    away_id = _team_id_by_name(conn, workspace_id, away_name)
    hits = dedupe.find_match_duplicates(
        conn, workspace_id, source_system=source_system, source_ref=m.source_ref,
        match_date=m.match_date, home_team_id=home_id, away_team_id=away_id)
    if not hits:
        return {"classification": "new", "match_id": None, "confidence": None, "reasons": []}
    top = hits[0]
    if "same source identifier" in top["reasons"]:
        cls = "existing"
    elif top["kind"] == "exact":
        cls = "additional_evidence"      # same fixture from a different source
    else:
        cls = "possible_duplicate"
    return {"classification": cls, "match_id": top["match_id"], "confidence": top["confidence"],
            "reasons": top["reasons"]}


def _serialise_candidate(m: CanonicalMatch, ds: CanonicalDataset, cls: dict[str, Any]) -> dict[str, Any]:
    names = _team_names(ds)
    return {
        "match": {k: (v.isoformat() if hasattr(v, "isoformat") else v)
                  for k, v in asdict(m).items() if not isinstance(v, list)},
        "home_team_name": names.get(m.home_team_ref),
        "away_team_name": names.get(m.away_team_ref),
        "evidence": {k: cls[k] for k in ("classification", "confidence", "reasons")},
    }


def _upsert_item(conn: Connection, workspace_id: UUID, *, source_id: UUID | None, source_system: str,
                 source_ref: str, kind: str, classification: str, confidence: float | None,
                 match_id: UUID | None, candidate: dict[str, Any], status: str,
                 proposed_changes: dict[str, Any] | None = None) -> UUID:
    existing = conn.execute(
        text("SELECT id FROM discovery_item WHERE workspace_id = :w AND source_system = :ss "
             "AND source_ref = :sr AND kind = :k"),
        {"w": workspace_id, "ss": source_system, "sr": source_ref, "k": kind},
    ).scalar_one_or_none()
    params = {"cl": classification, "cf": confidence, "mid": match_id, "ca": json.dumps(candidate),
              "st": status, "pc": json.dumps(proposed_changes) if proposed_changes is not None else None}
    if existing is not None:
        conn.execute(text("UPDATE discovery_item SET classification = :cl, confidence = :cf, match_id = :mid, "
                          "candidate = CAST(:ca AS jsonb), status = :st, proposed_changes = CAST(:pc AS jsonb), "
                          "updated_at = now() WHERE id = :id"), {**params, "id": existing})
        return existing
    return conn.execute(
        text("INSERT INTO discovery_item(workspace_id, source_id, source_system, source_ref, kind, "
             "classification, confidence, match_id, candidate, proposed_changes, status) "
             "VALUES (:w, :sid, :ss, :sr, :k, :cl, :cf, :mid, CAST(:ca AS jsonb), CAST(:pc AS jsonb), :st) RETURNING id"),
        {"w": workspace_id, "sid": source_id, "ss": source_system, "sr": source_ref, "k": kind, **params},
    ).scalar_one()


# ---- new-match discovery (9.5) --------------------------------------------------------------------

def discover_new(conn: Connection, workspace_id: UUID, actor: str, *, connector: Any,
                 source_id: UUID | None = None, mode: str = "review_required", can_approve: bool = False,
                 cursor: Any = None, scope_key: str = "new", scope: dict[str, Any] | None = None) -> dict[str, Any]:
    """Poll a connector for new matches, classify each, and either queue them for review (default) or
    — in authorised mode with approve permission — import (draft) and approve. Records coverage and
    source health. Reuses dedupe + the import pipeline; never merges or double-counts."""
    if mode not in SYNC_MODES:
        raise ValueError("invalid_sync_mode")
    try:
        batch = connector.fetch_new(cursor)
    except Exception as exc:  # noqa: BLE001 - a source failure is health, not "no matches"
        if source_id is not None:
            sources.record_health(conn, workspace_id, actor, source_id, reliability="down", notes=str(exc)[:200])
        record_coverage(conn, workspace_id, actor, source_id=source_id, scope_key=scope_key, scope=scope,
                        status="failed", notes=str(exc)[:200])
        return {"error": str(exc), "status": "failed"}

    ds = batch.dataset
    names = _team_names(ds)
    counts = {"new": 0, "existing": 0, "possible_duplicate": 0, "additional_evidence": 0, "insufficient": 0}
    queued = imported = 0
    for m in ds.matches:
        cls = classify_match(conn, workspace_id, ds.provenance.source_system, m, names)
        name = cls["classification"]
        counts[name] = counts.get(name, 0) + 1
        if name == "existing":
            # already imported from THIS source — nothing to queue; never re-opens an accepted item
            continue
        auto = (mode == AUTHORISED_AUTOMATIC and can_approve and name == "new")
        _upsert_item(conn, workspace_id, source_id=source_id, source_system=ds.provenance.source_system,
                     source_ref=m.source_ref, kind="new_match", classification=name,
                     confidence=cls["confidence"], match_id=cls["match_id"],
                     candidate=_serialise_candidate(m, ds, cls),
                     status="auto_imported" if auto else "pending_review")
        if auto:
            _import_match(conn, workspace_id, actor, m, ds, approve=True)
            imported += 1
        else:
            queued += 1

    if source_id is not None:
        sources.record_success(conn, source_id)
    record_coverage(conn, workspace_id, actor, source_id=source_id, scope_key=scope_key, scope=scope,
                    status="searched", matches_found=len(ds.matches))
    audit.write_audit(conn, workspace_id, actor, "autosync.discover_new", entity="workspace",
                      entity_id=str(workspace_id), after={"counts": counts, "queued": queued, "imported": imported})
    return {"status": "ok", "counts": counts, "queued": queued, "auto_imported": imported,
            "cursor": asdict(batch.cursor)}


# ---- updated-scorecard detection (9.6) ------------------------------------------------------------

def discover_updated(conn: Connection, workspace_id: UUID, actor: str, *, connector: Any,
                     source_id: UUID | None = None, cursor: Any = None) -> dict[str, Any]:
    """Detect meaningful changes to matches already recorded from this source. Queues a proposed
    change for review; NEVER overwrites a scorecard (acceptance goes through the revision/approval
    workflow, preserving the last approved statistics)."""
    batch = connector.fetch_updated(cursor)
    ds = batch.dataset
    changed = 0
    for m in ds.matches:
        existing = conn.execute(
            text("SELECT id FROM match WHERE source_system = :ss AND source_ref = :sr"),
            {"ss": ds.provenance.source_system, "sr": m.source_ref},
        ).scalar_one_or_none()
        if existing is None:
            continue   # not previously discovered from this source — a 'new' concern, not an update
        prior = conn.execute(
            text("SELECT recorded_fields FROM match_source WHERE match_id = :m AND source_system = :ss "
                 "AND source_ref = :sr"),
            {"m": existing, "ss": ds.provenance.source_system, "sr": m.source_ref},
        ).scalar_one_or_none() or {}
        # compare like-for-like: the source's fields in the SAME schema as the stored recorded_fields
        # (both are the pipeline's match-norm), so only genuine changes show — not key-name mismatches.
        new_fields = {k: v for k, v in pipeline._match_norm(m).items() if v is not None}
        diffs = {k: {"was": prior.get(k), "now": new_fields[k]}
                 for k in new_fields if str(prior.get(k)) != str(new_fields[k])}
        if not diffs:
            continue
        _upsert_item(conn, workspace_id, source_id=source_id, source_system=ds.provenance.source_system,
                     source_ref=m.source_ref, kind="updated_scorecard", classification="conflicting"
                     if _match_is_approved(conn, existing) else "additional_evidence", confidence=None,
                     match_id=existing, candidate=_serialise_candidate(m, ds, {"classification": "existing",
                     "confidence": None, "reasons": ["updated by source"]}),
                     status="pending_review", proposed_changes=diffs)
        changed += 1
    audit.write_audit(conn, workspace_id, actor, "autosync.discover_updated", entity="workspace",
                      entity_id=str(workspace_id), after={"changed": changed})
    return {"status": "ok", "changed": changed}


def _match_is_approved(conn: Connection, match_id: UUID) -> bool:
    return conn.execute(text("SELECT approval_status = 'approved' FROM match WHERE id = :m"),
                        {"m": match_id}).scalar_one_or_none() or False


# ---- import + review actions (9.8) ----------------------------------------------------------------

def _dataset_from_candidate(candidate: dict[str, Any], source_system: str) -> CanonicalDataset:
    mdata = dict(candidate["match"])
    md = mdata.get("match_date")
    match_date = date.fromisoformat(md) if isinstance(md, str) else md
    home_ref, away_ref = mdata.get("home_team_ref"), mdata.get("away_team_ref")
    ds = CanonicalDataset(provenance=SourceProvenance(source_system=source_system))
    for ref, name in ((home_ref, candidate.get("home_team_name")), (away_ref, candidate.get("away_team_name"))):
        if ref:
            ds.clubs.append(CanonicalClub(source_ref=ref, name=name))
            ds.teams.append(CanonicalTeam(source_ref=ref, name=name, club_ref=ref))
    ds.matches.append(CanonicalMatch(
        source_ref=mdata["source_ref"], match_date=match_date,
        date_precision=mdata.get("date_precision", "exact" if match_date else "unknown"),
        home_team_ref=home_ref, away_team_ref=away_ref,
        competition_ref=mdata.get("competition_ref"), grade_ref=mdata.get("grade_ref"),
        venue_ref=mdata.get("venue_ref"), round=mdata.get("round"), match_format=mdata.get("match_format"),
        result_code=mdata.get("result_code"), result_type=mdata.get("result_type"),
        result_status=mdata.get("result_status", "unresolved")))
    return ds


def _import_match(conn: Connection, workspace_id: UUID, actor: str, m: CanonicalMatch,
                  ds: CanonicalDataset, *, approve: bool) -> UUID | None:
    """Import a single discovered match (as draft) through the shared pipeline; optionally approve."""
    mini = CanonicalDataset(provenance=ds.provenance)
    mini.matches = [m]
    refs = {m.home_team_ref, m.away_team_ref}
    mini.teams = [t for t in ds.teams if t.source_ref in refs]
    mini.clubs = [c for c in ds.clubs if c.source_ref in {t.club_ref for t in mini.teams}]
    # ensure every team has a club so it can be promoted
    have = {c.source_ref for c in mini.clubs}
    for t in mini.teams:
        if t.club_ref and t.club_ref not in have:
            mini.clubs.append(CanonicalClub(source_ref=t.club_ref, name=t.name))
            have.add(t.club_ref)
    pipeline.import_dataset(conn, workspace_id, actor, dataset=mini, commit=True)
    mid = conn.execute(text("SELECT id FROM match WHERE source_system = :ss AND source_ref = :sr"),
                       {"ss": ds.provenance.source_system, "sr": m.source_ref}).scalar_one_or_none()
    if approve and mid is not None:
        matches.set_approval(conn, workspace_id, actor, mid, status="approved",
                             reason="auto-imported by authorised AutoSync")
        recalc.recompute_match(conn, workspace_id, actor, mid)
    return mid


def get_item(conn: Connection, item_id: UUID) -> dict[str, Any] | None:
    r = conn.execute(text("SELECT * FROM discovery_item WHERE id = :id"), {"id": item_id}).mappings().first()
    return dict(r) if r else None


def list_items(conn: Connection, workspace_id: UUID, *, status: str | None = "pending_review",
               limit: int = 200) -> list[dict[str, Any]]:
    sql = "SELECT * FROM discovery_item WHERE workspace_id = :w"
    params: dict[str, Any] = {"w": workspace_id, "lim": limit}
    if status:
        sql += " AND status = :st"
        params["st"] = status
    sql += " ORDER BY created_at DESC LIMIT :lim"
    return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]


def accept_item(conn: Connection, workspace_id: UUID, actor: str, item_id: UUID) -> dict[str, Any]:
    """Accept a queued discovery. A **new** match is imported as a DRAFT (Phase 7 approval still
    governs official statistics). A discovery that links to an **existing** match (possible duplicate,
    additional evidence, or an updated scorecard) is recorded as an **additional source** on that
    match (R1) — never creating a duplicate match and never overwriting the scorecard. Idempotent;
    preserves provenance."""
    item = get_item(conn, item_id)
    if item is None:
        raise ValueError("item_not_found")
    if item["status"] not in ("pending_review",):
        return item
    if item["match_id"] is not None:
        # confirm it is the same match: attach this source as evidence, do NOT create a new match.
        # Store the source's fields in the same match-norm schema the importer uses, so conflicting
        # accounts across sources line up field-for-field for review.
        ds = _dataset_from_candidate(item["candidate"], item["source_system"])
        norm = pipeline._match_norm(ds.matches[0]) if ds.matches else {}
        match_sources.attach_source(conn, workspace_id, actor, item["match_id"],
                                    source_system=item["source_system"], source_ref=item["source_ref"],
                                    recorded_fields=norm)
        mid = item["match_id"]
    else:
        ds = _dataset_from_candidate(item["candidate"], item["source_system"])
        pipeline.import_dataset(conn, workspace_id, actor, dataset=ds, commit=True)
        mid = conn.execute(text("SELECT id FROM match WHERE source_system = :ss AND source_ref = :sr"),
                           {"ss": item["source_system"], "sr": item["source_ref"]}).scalar_one_or_none()
    conn.execute(text("UPDATE discovery_item SET status = 'accepted', match_id = :m, reviewed_by = :by, "
                      "reviewed_at = now(), updated_at = now() WHERE id = :id"),
                 {"m": mid, "by": actor, "id": item_id})
    audit.write_audit(conn, workspace_id, actor, "autosync.item_accepted", entity="discovery_item", entity_id=str(item_id))
    return get_item(conn, item_id)


def reject_item(conn: Connection, workspace_id: UUID, actor: str, item_id: UUID, *, notes: str | None = None) -> dict[str, Any]:
    conn.execute(text("UPDATE discovery_item SET status = 'rejected', reviewed_by = :by, reviewed_at = now(), "
                      "notes = :n, updated_at = now() WHERE id = :id AND status = 'pending_review'"),
                 {"by": actor, "n": notes, "id": item_id})
    audit.write_audit(conn, workspace_id, actor, "autosync.item_rejected", entity="discovery_item", entity_id=str(item_id))
    return get_item(conn, item_id)


def bulk_review(conn: Connection, workspace_id: UUID, actor: str, item_ids: list[UUID], *, action: str,
                notes: str | None = None) -> dict[str, int]:
    """Accept or reject many queued discoveries at once — each preserving its own provenance,
    validation, permissions and audit. Large historical datasets without thousands of clicks."""
    if action not in ("accept", "reject"):
        raise ValueError("invalid_bulk_action")
    done = 0
    for iid in item_ids:
        if action == "accept":
            accept_item(conn, workspace_id, actor, iid)
        else:
            reject_item(conn, workspace_id, actor, iid, notes=notes)
        done += 1
    return {"action": action, "count": done}
