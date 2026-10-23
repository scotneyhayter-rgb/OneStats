"""Person-affiliation endpoints — roles & participation (Phase 5, Stage 2).

Workspace-scoped, gated by ``person.manage``, audited. Affiliation is membership/involvement,
not match participation. ``role`` is free text (extensible); periods may be unknown/approximate.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from onestats.api.deps import RequestContext, SettingsDep, require_permission
from onestats.db.session import get_engine
from onestats.db.workspace import workspace_transaction
from onestats.domain import affiliations

router = APIRouter(prefix="/workspaces/{workspace_id}/affiliations", tags=["affiliations"])

AffCtx = Annotated[RequestContext, Depends(require_permission("person.manage"))]

_VALUE_ERR_STATUS = {
    "person_not_found": status.HTTP_404_NOT_FOUND,
    "organisation_not_found": status.HTTP_404_NOT_FOUND,
    "affiliation_not_found": status.HTTP_404_NOT_FOUND,
    "team_not_in_organisation": status.HTTP_409_CONFLICT,
    "invalid_verification_status": status.HTTP_400_BAD_REQUEST,
    "invalid_date_range": status.HTTP_400_BAD_REQUEST,
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


class AffiliationCreate(BaseModel):
    person_id: UUID
    organisation_id: UUID
    role: str = Field(default="player", min_length=1, max_length=100)
    team_id: UUID | None = None
    competition_id: UUID | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    date_approx: bool = False
    is_representative: bool = False
    verification_status: str = Field(default="unverified", pattern="^(unverified|verified|disputed|corrected)$")
    evidence: str | None = None
    notes: str | None = None
    source_system: str | None = None
    source_ref: str | None = None


class AffiliationCorrect(BaseModel):
    role: str | None = Field(default=None, max_length=100)
    team_id: UUID | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    set_dates: bool = False
    date_approx: bool | None = None
    is_representative: bool | None = None
    status: str | None = None
    evidence: str | None = None
    notes: str | None = None


class VerificationSet(BaseModel):
    verification_status: str = Field(pattern="^(unverified|verified|disputed|corrected)$")


@router.post("", status_code=status.HTTP_201_CREATED)
def create_affiliation(workspace_id: UUID, body: AffiliationCreate, settings: SettingsDep, ctx: AffCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            aid = affiliations.create_affiliation(
                conn, workspace_id, str(ctx.user["id"]), person_id=body.person_id,
                organisation_id=body.organisation_id, role=body.role, team_id=body.team_id,
                competition_id=body.competition_id, valid_from=body.valid_from, valid_to=body.valid_to,
                date_approx=body.date_approx, is_representative=body.is_representative,
                verification_status=body.verification_status, evidence=body.evidence, notes=body.notes,
                source_system=body.source_system, source_ref=body.source_ref,
            )
        except ValueError as exc:
            raise _value_error(exc) from exc
        return _ids(affiliations.get_affiliation(conn, aid))


@router.get("")
def list_affiliations(
    workspace_id: UUID, settings: SettingsDep, ctx: AffCtx,
    person_id: UUID | None = None, organisation_id: UUID | None = None, role: str | None = None,
) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return [_ids(a) for a in affiliations.list_affiliations(
            conn, person_id=person_id, organisation_id=organisation_id, role=role)]


@router.get("/as-of")
def as_of(workspace_id: UUID, person_id: UUID, on_date: date, settings: SettingsDep, ctx: AffCtx) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return [_ids(a) for a in affiliations.affiliations_as_of(conn, person_id, on_date)]


@router.get("/{affiliation_id}")
def get_affiliation(workspace_id: UUID, affiliation_id: UUID, settings: SettingsDep, ctx: AffCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        a = affiliations.get_affiliation(conn, affiliation_id)
        if a is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "affiliation_not_found")
        return _ids(a)


@router.patch("/{affiliation_id}")
def correct_affiliation(workspace_id: UUID, affiliation_id: UUID, body: AffiliationCorrect, settings: SettingsDep, ctx: AffCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _ids(affiliations.correct_affiliation(
                conn, workspace_id, str(ctx.user["id"]), affiliation_id,
                role=body.role, team_id=body.team_id, valid_from=body.valid_from, valid_to=body.valid_to,
                set_dates=body.set_dates, date_approx=body.date_approx,
                is_representative=body.is_representative, status=body.status,
                evidence=body.evidence, notes=body.notes,
            ))
        except ValueError as exc:
            raise _value_error(exc) from exc


@router.post("/{affiliation_id}/verification")
def set_verification(workspace_id: UUID, affiliation_id: UUID, body: VerificationSet, settings: SettingsDep, ctx: AffCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _ids(affiliations.set_verification(
                conn, workspace_id, str(ctx.user["id"]), affiliation_id, status=body.verification_status))
        except ValueError as exc:
            raise _value_error(exc) from exc
