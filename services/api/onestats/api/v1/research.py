"""Research Centre API (Phase 10). Workspace-scoped, gated by ``research.manage``, audited.

Research projects, the Source Library and a real-data dashboard. Historical reconstruction reuses the
Phase 6 scorecard tables and Phase 7 approval; nothing here enters official statistics without the
existing approval workflow.
"""
from __future__ import annotations

from datetime import date
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from onestats.api.deps import RequestContext, SettingsDep, require_permission
from onestats.db.session import get_engine
from onestats.db.workspace import workspace_transaction
from onestats.domain import matches as matches_domain
from onestats.domain.research import (
    aliases,
    assist,
    dashboard,
    extraction,
    gaps,
    notes,
    projects,
    provenance,
    reconstruction,
    sources,
    storage,
    tasks,
    timeline,
)

router = APIRouter(prefix="/workspaces/{workspace_id}/research", tags=["research"])
Ctx = Annotated[RequestContext, Depends(require_permission("research.manage"))]
VerifyCtx = Annotated[RequestContext, Depends(require_permission("research.verify"))]

# Research verification decisions mapped onto the Phase 7 approval state machine (no parallel machine).
_VERIFY_MAP = {
    "approved": "approved",            # fully verified
    "verified_partial": "verified_partial",  # verified as far as it goes (known-incomplete)
    "disputed": "disputed",            # unresolved conflict — held out of official statistics
    "rejected": "rejected",            # unsupported — returned
    "reopen": "draft",                 # send back for further research
}

_ERRORS = {
    "title_required": status.HTTP_400_BAD_REQUEST,
    "invalid_status": status.HTTP_400_BAD_REQUEST,
    "invalid_source_type": status.HTTP_400_BAD_REQUEST,
    "invalid_date_precision": status.HTTP_400_BAD_REQUEST,
    "invalid_ocr_status": status.HTTP_400_BAD_REQUEST,
    "project_not_found": status.HTTP_404_NOT_FOUND,
    "field_path_required": status.HTTP_400_BAD_REQUEST,
    "claim_not_found": status.HTTP_404_NOT_FOUND,
    "source_not_found": status.HTTP_404_NOT_FOUND,
    "no_file": status.HTTP_409_CONFLICT,
    "extraction_not_found": status.HTTP_404_NOT_FOUND,
    "invalid_assessed_class": status.HTTP_400_BAD_REQUEST,
    "match_not_found": status.HTTP_404_NOT_FOUND,
    "task_not_found": status.HTTP_404_NOT_FOUND,
    "body_required": status.HTTP_400_BAD_REQUEST,
    "invalid_evidence_class": status.HTTP_400_BAD_REQUEST,
    "invalid_entity_type": status.HTTP_400_BAD_REQUEST,
    "alias_required": status.HTTP_400_BAD_REQUEST,
}


def _engine(settings):
    eng = get_engine(settings)
    if eng is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database not configured")
    return eng


def _err(exc: ValueError) -> HTTPException:
    return HTTPException(_ERRORS.get(str(exc), status.HTTP_400_BAD_REQUEST), str(exc))


def _s(d: dict[str, Any]) -> dict[str, Any]:
    return {k: (str(v) if isinstance(v, UUID) else v) for k, v in d.items()}


class ProjectCreate(BaseModel):
    title: str
    description: str | None = None
    scope: dict[str, Any] | None = None
    owner: str | None = None
    status: str = Field(default="active", pattern="^(active|paused|completed|archived)$")


class ProjectUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    scope: dict[str, Any] | None = None
    owner: str | None = None
    status: str | None = Field(default=None, pattern="^(active|paused|completed|archived)$")


class SourceCreate(BaseModel):
    title: str
    source_type: str
    publication: str | None = None
    author: str | None = None
    publication_date: date | None = None
    publication_date_precision: str | None = Field(
        default=None, pattern="^(exact|month|year|approximate|range|unknown)$")
    edition: str | None = None
    page_ref: str | None = None
    original_url: str | None = None
    archive_ref: str | None = None
    source_identifier: str | None = None
    language: str | None = None
    location: str | None = None
    copyright_status: str | None = None
    usage_restrictions: str | None = None
    date_accessed: date | None = None
    notes: str | None = None


class LinkMatch(BaseModel):
    match_id: UUID
    role: str | None = None


@router.get("/dashboard")
def get_dashboard(workspace_id: UUID, settings: SettingsDep, ctx: Ctx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return dashboard.dashboard_summary(conn, workspace_id)


@router.get("/projects")
def list_projects(workspace_id: UUID, settings: SettingsDep, ctx: Ctx,
                  status_filter: str | None = None) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return [_s(r) for r in projects.list_projects(conn, workspace_id, status=status_filter)]


@router.post("/projects", status_code=status.HTTP_201_CREATED)
def create_project(workspace_id: UUID, body: ProjectCreate, settings: SettingsDep, ctx: Ctx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _s(projects.create_project(conn, workspace_id, str(ctx.user["id"]), **body.model_dump()))
        except ValueError as exc:
            raise _err(exc) from exc


@router.get("/projects/{project_id}")
def get_project(workspace_id: UUID, project_id: UUID, settings: SettingsDep, ctx: Ctx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        proj = projects.get_project(conn, project_id)
        if proj is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "project_not_found")
        return _s(proj)


@router.patch("/projects/{project_id}")
def update_project(workspace_id: UUID, project_id: UUID, body: ProjectUpdate,
                   settings: SettingsDep, ctx: Ctx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _s(projects.update_project(conn, workspace_id, str(ctx.user["id"]), project_id,
                                              **body.model_dump(exclude_none=True)))
        except ValueError as exc:
            raise _err(exc) from exc


@router.get("/sources")
def list_sources(workspace_id: UUID, settings: SettingsDep, ctx: Ctx,
                 source_type: str | None = None, limit: int = 200, offset: int = 0) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return [_s(r) for r in sources.list_sources(conn, workspace_id, source_type=source_type,
                                                    limit=limit, offset=offset)]


@router.post("/sources", status_code=status.HTTP_201_CREATED)
def create_source(workspace_id: UUID, body: SourceCreate, settings: SettingsDep, ctx: Ctx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _s(sources.create_source(conn, workspace_id, str(ctx.user["id"]), **body.model_dump()))
        except ValueError as exc:
            raise _err(exc) from exc


@router.get("/sources/{source_id}")
def get_source(workspace_id: UUID, source_id: UUID, settings: SettingsDep, ctx: Ctx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        src = sources.get_source(conn, source_id)
        if src is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "source_not_found")
        return _s(src)


@router.post("/sources/{source_id}/file", status_code=status.HTTP_201_CREATED)
async def upload_source_file(workspace_id: UUID, source_id: UUID, settings: SettingsDep, ctx: Ctx,
                             file: UploadFile) -> dict[str, Any]:
    """Upload the original document for a source (image/PDF). Stored unaltered; integrity hash recorded;
    duplicate-by-content is reported, not blocked."""
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        if sources.get_source(conn, source_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "source_not_found")
    raw = await file.read()
    try:
        stored = storage.store_source_file(settings, workspace_id, raw, file.content_type or "")
    except storage.SourceFileError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return _s(sources.set_file(conn, workspace_id, str(ctx.user["id"]), source_id,
                                   file_ref=str(stored["file_ref"]), file_sha256=str(stored["file_sha256"]),
                                   file_bytes=int(stored["file_bytes"]), content_type=str(stored["content_type"])))


@router.get("/sources/{source_id}/file")
def get_source_file(workspace_id: UUID, source_id: UUID, settings: SettingsDep, ctx: Ctx):
    """Serve a source's original document (for the document viewer, Stage 10.5). If the source has been
    promoted into the media archive (Phase 11), the file now lives there — serve it from the asset."""
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        src = sources.get_source(conn, source_id)
        if src is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "no_file")
        if not src.get("file_ref") and src.get("media_asset_id"):
            from onestats.domain.media import assets as media_assets
            from onestats.domain.media import providers as media_providers
            asset = media_assets.get_asset(conn, src["media_asset_id"])
            if asset and asset["storage_provider"] == "internal" and asset.get("storage_locator"):
                mpath = media_providers.internal_provider().path(settings, workspace_id, asset["storage_locator"])
                if mpath is not None:
                    return FileResponse(str(mpath), media_type=asset.get("content_type") or "application/octet-stream")
    if not src.get("file_ref"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no_file")
    path = storage.source_file_path(settings, workspace_id, src["file_ref"])
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no_file")
    return FileResponse(str(path), media_type=src.get("content_type") or "application/octet-stream")


@router.get("/publications/{publication}/editions")
def list_editions(workspace_id: UUID, publication: str, settings: SettingsDep, ctx: Ctx) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return [_s(r) for r in sources.list_editions(conn, workspace_id, publication)]


class Extract(BaseModel):
    page: int = 1
    language: str | None = None


class ManualTranscription(BaseModel):
    text_value: str
    page: int = 1


class Correction(BaseModel):
    corrected_text: str


@router.get("/sources/{source_id}/extractions")
def list_extractions(workspace_id: UUID, source_id: UUID, settings: SettingsDep, ctx: Ctx) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return [_s(r) for r in extraction.list_for_source(conn, workspace_id, source_id)]


@router.post("/sources/{source_id}/extract", status_code=status.HTTP_201_CREATED)
def extract_source(workspace_id: UUID, source_id: UUID, body: Extract, settings: SettingsDep, ctx: Ctx) -> dict[str, Any]:
    """Run local OCR on the stored document. Falls back to a manual-transcription placeholder when no
    local OCR engine is installed (never a paid cloud provider without approval)."""
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _s(extraction.extract_source(conn, settings, workspace_id, str(ctx.user["id"]), source_id,
                                                page=body.page, language=body.language))
        except ValueError as exc:
            raise _err(exc) from exc


@router.post("/sources/{source_id}/transcription", status_code=status.HTTP_201_CREATED)
def manual_transcription(workspace_id: UUID, source_id: UUID, body: ManualTranscription,
                         settings: SettingsDep, ctx: Ctx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _s(extraction.record_manual(conn, workspace_id, str(ctx.user["id"]), source_id,
                                               text_value=body.text_value, page=body.page))
        except ValueError as exc:
            raise _err(exc) from exc


@router.post("/extractions/{extraction_id}/correct")
def correct_extraction(workspace_id: UUID, extraction_id: UUID, body: Correction,
                       settings: SettingsDep, ctx: Ctx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _s(extraction.set_correction(conn, workspace_id, str(ctx.user["id"]), extraction_id,
                                                body.corrected_text))
        except ValueError as exc:
            raise _err(exc) from exc


@router.post("/sources/{source_id}/link")
def link_source_match(workspace_id: UUID, source_id: UUID, body: LinkMatch,
                      settings: SettingsDep, ctx: Ctx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return _s(sources.link_match(conn, workspace_id, str(ctx.user["id"]), source_id, body.match_id,
                                     role=body.role))


@router.get("/matches/{match_id}/sources")
def match_sources(workspace_id: UUID, match_id: UUID, settings: SettingsDep, ctx: Ctx) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return [_s(r) for r in sources.list_sources_for_match(conn, workspace_id, match_id)]


class StartReconstruction(BaseModel):
    competition_id: UUID | None = None
    grade_id: UUID | None = None
    season_id: UUID | None = None
    venue_id: UUID | None = None
    match_date: date | None = None
    date_precision: str = Field(default="unknown", pattern="^(unknown|exact|year|month|approx|range|season)$")
    match_date_end: date | None = None
    notes: str | None = None
    source_id: UUID | None = None
    source_role: str | None = "primary"


class AttachSource(BaseModel):
    source_id: UUID
    role: str | None = None


@router.post("/reconstructions", status_code=status.HTTP_201_CREATED)
def start_reconstruction(workspace_id: UUID, body: StartReconstruction, settings: SettingsDep, ctx: Ctx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _s(reconstruction.start_reconstruction(conn, workspace_id, str(ctx.user["id"]), **body.model_dump()))
        except ValueError as exc:
            raise _err(exc) from exc


@router.get("/matches")
def list_research_matches(workspace_id: UUID, settings: SettingsDep, ctx: Ctx,
                          approval_status: str | None = None) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return reconstruction.list_matches_under_research(conn, workspace_id, approval_status=approval_status)


@router.post("/matches/{match_id}/attach-source")
def attach_source(workspace_id: UUID, match_id: UUID, body: AttachSource, settings: SettingsDep, ctx: Ctx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return _s(reconstruction.attach_source(conn, workspace_id, str(ctx.user["id"]), match_id, body.source_id,
                                               role=body.role))


@router.get("/matches/{match_id}/reconstruction")
def reconstruction_summary(workspace_id: UUID, match_id: UUID, settings: SettingsDep, ctx: Ctx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return reconstruction.summary(conn, workspace_id, match_id)
        except ValueError as exc:
            raise _err(exc) from exc


class Verify(BaseModel):
    decision: str = Field(pattern="^(approved|verified_partial|disputed|rejected|reopen)$")
    reason: str | None = None


@router.post("/matches/{match_id}/submit-for-review")
def submit_for_review(workspace_id: UUID, match_id: UUID, body: Verify | None = None,
                      *, settings: SettingsDep, ctx: Ctx) -> dict[str, Any]:
    """A researcher submits a reconstruction for verification (draft -> awaiting_approval)."""
    reason = body.reason if body else None
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _s(matches_domain.set_approval(conn, workspace_id, str(ctx.user["id"]), match_id,
                                                  status="awaiting_approval", reason=reason))
        except ValueError as exc:
            raise _err(exc) from exc


@router.post("/matches/{match_id}/verify")
def verify_match(workspace_id: UUID, match_id: UUID, body: Verify, settings: SettingsDep,
                 ctx: VerifyCtx) -> dict[str, Any]:
    """An authorised reviewer records a verification decision. Maps to the Phase 7 approval machine;
    only verified states feed official statistics, and a verified_partial record contributes only the
    data it actually has. 'disputed' is held out of statistics until resolved."""
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _s(matches_domain.set_approval(conn, workspace_id, str(ctx.user["id"]), match_id,
                                                  status=_VERIFY_MAP[body.decision], reason=body.reason))
        except ValueError as exc:
            raise _err(exc) from exc


class AliasCreate(BaseModel):
    entity_type: str = Field(pattern="^(club|competition|grade|team|person|venue|place|other)$")
    alias: str
    entity_id: UUID | None = None
    alias_kind: str | None = None
    language: str | None = None
    note: str | None = None


@router.get("/aliases")
def list_aliases(workspace_id: UUID, settings: SettingsDep, ctx: Ctx, entity_type: str | None = None,
                 entity_id: UUID | None = None) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return [_s(r) for r in aliases.list_aliases(conn, workspace_id, entity_type=entity_type, entity_id=entity_id)]


@router.post("/aliases", status_code=status.HTTP_201_CREATED)
def create_alias(workspace_id: UUID, body: AliasCreate, settings: SettingsDep, ctx: Ctx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _s(aliases.register_alias(conn, workspace_id, str(ctx.user["id"]), **body.model_dump()))
        except ValueError as exc:
            raise _err(exc) from exc


@router.get("/aliases/expand")
def expand_terms(workspace_id: UUID, term: str, settings: SettingsDep, ctx: Ctx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return {"term": term, "expanded": aliases.expand_terms(conn, workspace_id, term)}


class TaskCreate(BaseModel):
    title: str
    description: str | None = None
    project_id: UUID | None = None
    gap_kind: str | None = None
    scope: dict[str, Any] | None = None
    priority: int = 0
    assigned_to: str | None = None


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    priority: int | None = None
    assigned_to: str | None = None
    status: str | None = Field(default=None, pattern="^(open|in_progress|resolved|dismissed)$")


class NoteCreate(BaseModel):
    body: str
    evidence_class: str = Field(default="unverified", pattern="^(verified|supported|oral_history|unverified|disputed)$")
    project_id: UUID | None = None
    match_id: UUID | None = None
    source_id: UUID | None = None


@router.get("/tasks")
def list_tasks(workspace_id: UUID, settings: SettingsDep, ctx: Ctx, project_id: UUID | None = None,
               status_filter: str | None = None) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return [_s(r) for r in tasks.list_tasks(conn, workspace_id, project_id=project_id, status=status_filter)]


@router.post("/tasks", status_code=status.HTTP_201_CREATED)
def create_task(workspace_id: UUID, body: TaskCreate, settings: SettingsDep, ctx: Ctx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _s(tasks.create_task(conn, workspace_id, str(ctx.user["id"]), **body.model_dump()))
        except ValueError as exc:
            raise _err(exc) from exc


@router.patch("/tasks/{task_id}")
def update_task(workspace_id: UUID, task_id: UUID, body: TaskUpdate, settings: SettingsDep, ctx: Ctx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _s(tasks.update_task(conn, workspace_id, str(ctx.user["id"]), task_id,
                                        **body.model_dump(exclude_none=True)))
        except ValueError as exc:
            raise _err(exc) from exc


@router.get("/notes")
def list_notes(workspace_id: UUID, settings: SettingsDep, ctx: Ctx, project_id: UUID | None = None,
               match_id: UUID | None = None, source_id: UUID | None = None) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return [_s(r) for r in notes.list_notes(conn, workspace_id, project_id=project_id, match_id=match_id,
                                                source_id=source_id)]


@router.post("/notes", status_code=status.HTTP_201_CREATED)
def create_note(workspace_id: UUID, body: NoteCreate, settings: SettingsDep, ctx: Ctx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _s(notes.create_note(conn, workspace_id, str(ctx.user["id"]), **body.model_dump()))
        except ValueError as exc:
            raise _err(exc) from exc


@router.get("/matches/{match_id}/suggestions")
def match_suggestions(workspace_id: UUID, match_id: UUID, settings: SettingsDep, ctx: Ctx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return assist.suggestions_for_match(conn, workspace_id, match_id)


class CoverageAssessment(BaseModel):
    season_id: UUID
    assessed_class: str = Field(pattern="^(comprehensive|partial|significant_gaps|unassessed|inactive)$")
    competition_id: UUID | None = None
    grade_id: UUID | None = None
    basis: str | None = None


@router.get("/timeline")
def research_timeline(workspace_id: UUID, settings: SettingsDep, ctx: Ctx,
                      competition_id: UUID | None = None) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return timeline.season_timeline(conn, workspace_id, competition_id=competition_id)


@router.post("/timeline/assessment")
def set_coverage_assessment(workspace_id: UUID, body: CoverageAssessment, settings: SettingsDep,
                            ctx: VerifyCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _s(timeline.set_assessment(conn, workspace_id, str(ctx.user["id"]), **body.model_dump()))
        except ValueError as exc:
            raise _err(exc) from exc


@router.get("/gaps")
def research_gaps(workspace_id: UUID, settings: SettingsDep, ctx: Ctx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return gaps.coverage_gaps(conn, workspace_id)


class ClaimCreate(BaseModel):
    field_path: str
    source_id: UUID | None = None
    claimed_value: str | None = None
    normalised_value: str | None = None
    confidence: float | None = None
    researcher: str | None = None


class Decision(BaseModel):
    note: str | None = None


@router.get("/matches/{match_id}/provenance")
def match_provenance(workspace_id: UUID, match_id: UUID, settings: SettingsDep, ctx: Ctx) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return [_s(r) for r in provenance.list_for_match(conn, workspace_id, match_id)]


@router.post("/matches/{match_id}/provenance", status_code=status.HTTP_201_CREATED)
def record_claim(workspace_id: UUID, match_id: UUID, body: ClaimCreate, settings: SettingsDep, ctx: Ctx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _s(provenance.record_claim(conn, workspace_id, str(ctx.user["id"]), match_id=match_id,
                                              **body.model_dump()))
        except ValueError as exc:
            raise _err(exc) from exc


@router.get("/matches/{match_id}/conflicts")
def match_conflicts(workspace_id: UUID, match_id: UUID, settings: SettingsDep, ctx: Ctx) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return [{"field_path": c["field_path"], "claims": [_s(x) for x in c["claims"]]}
                for c in provenance.field_conflicts(conn, workspace_id, match_id)]


@router.post("/provenance/{claim_id}/accept")
def accept_claim(workspace_id: UUID, claim_id: UUID, body: Decision, settings: SettingsDep, ctx: Ctx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _s(provenance.accept_claim(conn, workspace_id, str(ctx.user["id"]), claim_id, note=body.note))
        except ValueError as exc:
            raise _err(exc) from exc


@router.post("/provenance/{claim_id}/reject")
def reject_claim(workspace_id: UUID, claim_id: UUID, body: Decision, settings: SettingsDep, ctx: Ctx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _s(provenance.reject_claim(conn, workspace_id, str(ctx.user["id"]), claim_id, note=body.note))
        except ValueError as exc:
            raise _err(exc) from exc
