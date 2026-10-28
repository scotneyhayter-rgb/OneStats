"""Person identity-resolution endpoints (Phase 5, Stage 3).

The backend for a future Identity Resolution Centre: candidate detection, side-by-side compare,
administrator-approved reversible merge + undo, "definitely distinct" assertions, and a review
queue (pending / merged / distinct / deferred / rejected). Workspace-scoped, gated by
``person.manage``, audited. A name match never merges — every merge is an explicit admin action.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from onestats.api.deps import RequestContext, SettingsDep, require_permission
from onestats.db.session import get_engine
from onestats.db.workspace import workspace_transaction
from onestats.domain import person_resolution

router = APIRouter(prefix="/workspaces/{workspace_id}/identity", tags=["identity"])

IdCtx = Annotated[RequestContext, Depends(require_permission("person.manage"))]

_VALUE_ERR_STATUS = {
    "person_not_found": status.HTTP_404_NOT_FOUND,
    "merge_not_found": status.HTTP_404_NOT_FOUND,
    "review_not_found": status.HTTP_404_NOT_FOUND,
    "asserted_distinct": status.HTTP_409_CONFLICT,
    "already_merged": status.HTTP_409_CONFLICT,
    "canonical_already_merged": status.HTTP_409_CONFLICT,
    "already_undone": status.HTTP_409_CONFLICT,
    "cannot_merge_same": status.HTTP_409_CONFLICT,
    "same_person": status.HTTP_409_CONFLICT,
    "circular_merge": status.HTTP_409_CONFLICT,
    "review_already_decided": status.HTTP_409_CONFLICT,
    "canonical_must_be_one_of_the_pair": status.HTTP_400_BAD_REQUEST,
    "invalid_decision": status.HTTP_400_BAD_REQUEST,
}


def _engine(settings):
    eng = get_engine(settings)
    if eng is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database not configured")
    return eng


def _value_error(exc: ValueError) -> HTTPException:
    return HTTPException(_VALUE_ERR_STATUS.get(str(exc), status.HTTP_400_BAD_REQUEST), str(exc))


def _ids(d: dict[str, Any]) -> dict[str, Any]:
    return {k: (str(v) if isinstance(v, UUID) else v) for k, v in d.items()}


class DistinctAssert(BaseModel):
    person_a_id: UUID
    person_b_id: UUID
    reason: str | None = None
    evidence: str | None = None


class MergeRequest(BaseModel):
    canonical_person_id: UUID
    merged_person_id: UUID
    reason: str | None = None
    evidence: str | None = None


class ReviewCreate(BaseModel):
    person_a_id: UUID
    person_b_id: UUID
    confidence: str | None = None
    evidence: str | None = None
    notes: str | None = None


class ReviewDecision(BaseModel):
    decision: str = Field(pattern="^(merge|distinct|defer|reject)$")
    canonical_person_id: UUID | None = None
    reason: str | None = None
    evidence: str | None = None


@router.get("/candidates")
def candidates(workspace_id: UUID, person_id: UUID, settings: SettingsDep, ctx: IdCtx) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            cands = person_resolution.find_duplicate_candidates(conn, person_id)
        except ValueError as exc:
            raise _value_error(exc) from exc
        return [{**c, "person_id": str(c["person_id"])} for c in cands]


@router.get("/candidates/scan")
def candidates_scan(workspace_id: UUID, settings: SettingsDep, ctx: IdCtx) -> list[dict[str, Any]]:
    """Workspace-wide duplicate candidate pairs for the identity review worklist (strongest first)."""
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return [_ids(p) for p in person_resolution.scan_duplicate_pairs(conn, workspace_id)]


@router.get("/compare")
def compare(workspace_id: UUID, a: UUID, b: UUID, settings: SettingsDep, ctx: IdCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return person_resolution.compare(conn, a, b)
        except ValueError as exc:
            raise _value_error(exc) from exc


@router.post("/assert-distinct", status_code=status.HTTP_201_CREATED)
def assert_distinct(workspace_id: UUID, body: DistinctAssert, settings: SettingsDep, ctx: IdCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            aid = person_resolution.assert_distinct(
                conn, workspace_id, str(ctx.user["id"]), body.person_a_id, body.person_b_id,
                reason=body.reason, evidence=body.evidence)
        except ValueError as exc:
            raise _value_error(exc) from exc
        return {"assertion_id": str(aid), "asserted_distinct": True}


@router.post("/merge", status_code=status.HTTP_201_CREATED)
def merge(workspace_id: UUID, body: MergeRequest, settings: SettingsDep, ctx: IdCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _ids(person_resolution.merge_people(
                conn, workspace_id, str(ctx.user["id"]), body.canonical_person_id, body.merged_person_id,
                reason=body.reason, evidence=body.evidence))
        except ValueError as exc:
            raise _value_error(exc) from exc


@router.post("/merges/{merge_id}/undo")
def undo_merge(workspace_id: UUID, merge_id: UUID, settings: SettingsDep, ctx: IdCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _ids(person_resolution.undo_merge(conn, workspace_id, str(ctx.user["id"]), merge_id))
        except ValueError as exc:
            raise _value_error(exc) from exc


@router.get("/merges")
def list_merges(workspace_id: UUID, settings: SettingsDep, ctx: IdCtx, person_id: UUID | None = None) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return [_ids(m) for m in person_resolution.list_merges(conn, person_id=person_id)]


@router.post("/reviews", status_code=status.HTTP_201_CREATED)
def create_review(workspace_id: UUID, body: ReviewCreate, settings: SettingsDep, ctx: IdCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            rid = person_resolution.create_review(
                conn, workspace_id, str(ctx.user["id"]), body.person_a_id, body.person_b_id,
                confidence=body.confidence, evidence=body.evidence, notes=body.notes)
        except ValueError as exc:
            raise _value_error(exc) from exc
        return {"review_id": str(rid), "status": "pending"}


@router.get("/reviews")
def list_reviews(workspace_id: UUID, settings: SettingsDep, ctx: IdCtx, status_: str | None = None) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return [_ids(r) for r in person_resolution.list_reviews(conn, status=status_)]


@router.post("/reviews/{review_id}/decide")
def decide_review(workspace_id: UUID, review_id: UUID, body: ReviewDecision, settings: SettingsDep, ctx: IdCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return person_resolution.decide_review(
                conn, workspace_id, str(ctx.user["id"]), review_id, decision=body.decision,
                canonical_person_id=body.canonical_person_id, reason=body.reason, evidence=body.evidence)
        except ValueError as exc:
            raise _value_error(exc) from exc
