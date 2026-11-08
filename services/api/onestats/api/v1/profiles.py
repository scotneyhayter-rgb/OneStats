"""Player-profile endpoints (Phase 5, Stage 4).

Profile detail, player numbers, leadership, recognition and photographs hanging off person_id.
Workspace-scoped, gated by ``person.manage``, audited. Photos reuse the Phase 3 secure image
pipeline. Statistics are a reserved contract (never fabricated). A public career view strips
internal and non-public fields. The full People UI is Stage 6 — this is the backend only.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from onestats.api.deps import RequestContext, SettingsDep, require_permission
from onestats.core import images
from onestats.db.session import get_engine
from onestats.db.workspace import workspace_transaction
from onestats.domain import photos, profiles
from onestats.domain.records import player_profile

router = APIRouter(prefix="/workspaces/{workspace_id}/people", tags=["profiles"])

PCtx = Annotated[RequestContext, Depends(require_permission("person.manage"))]
ViewCtx = Annotated[RequestContext, Depends(require_permission("match.view"))]

_VALUE_ERR_STATUS = {
    "person_not_found": status.HTTP_404_NOT_FOUND,
    "organisation_not_found": status.HTTP_404_NOT_FOUND,
    "photo_not_found": status.HTTP_404_NOT_FOUND,
    "invalid_player_status": status.HTTP_400_BAD_REQUEST,
    "invalid_verification_status": status.HTTP_400_BAD_REQUEST,
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


class ProfileUpsert(BaseModel):
    full_name: str | None = None
    preferred_display_name: str | None = None
    biography: str | None = None
    research_notes: str | None = None
    date_of_death: date | None = None
    dod_precision: str | None = None
    batting_style: str | None = None
    bowling_style: str | None = None
    is_wicketkeeper: bool | None = None
    career_start: date | None = None
    career_end: date | None = None
    player_status: str | None = None
    verification_status: str | None = None
    public_visible: bool | None = None


class NumberAdd(BaseModel):
    organisation_id: UUID
    number: str | None = None
    season_label: str | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    note: str | None = None


class LeadershipAdd(BaseModel):
    organisation_id: UUID
    role: str = Field(min_length=1, max_length=100)
    team_id: UUID | None = None
    season_label: str | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    note: str | None = None


class RecognitionAdd(BaseModel):
    recognition_type: str = Field(min_length=1, max_length=100)
    organisation_id: UUID | None = None
    title: str | None = None
    awarded_on: date | None = None
    season_label: str | None = None
    evidence: str | None = None
    notes: str | None = None


class PhotoMeta(BaseModel):
    is_primary: bool = False
    caption: str | None = None
    approx_date: str | None = None
    source_attribution: str | None = None
    usage_permissions: str | None = None
    public_visible: bool = False


@router.get("/{person_id}/profile")
def get_profile(workspace_id: UUID, person_id: UUID, settings: SettingsDep, ctx: PCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        view = profiles.career_view(conn, person_id, workspace_id=workspace_id)
        if view is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "person_not_found")
        return view


@router.get("/{person_id}/public-profile")
def get_public_profile(workspace_id: UUID, person_id: UUID, settings: SettingsDep, ctx: PCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        view = profiles.career_view(conn, person_id, public=True, workspace_id=workspace_id)
        if view is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "not_public")
        return view


# --- Phase 13: profile statistics (composed from the one engine; view-gated) ---

@router.get("/{person_id}/career-stats")
def career_stats(workspace_id: UUID, person_id: UUID, settings: SettingsDep, ctx: ViewCtx,
                 competition_id: UUID | None = None, season_id: UUID | None = None) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return player_profile.career_summary(conn, workspace_id, person_id, competition_id=competition_id,
                                             season_id=season_id)


@router.get("/{person_id}/seasons")
def profile_seasons(workspace_id: UUID, person_id: UUID, settings: SettingsDep, ctx: ViewCtx) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return player_profile.season_breakdown(conn, workspace_id, person_id)


@router.get("/{person_id}/matches")
def profile_matches(workspace_id: UUID, person_id: UUID, settings: SettingsDep, ctx: ViewCtx,
                    limit: int = 500) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return player_profile.match_history(conn, workspace_id, person_id, limit=limit)


@router.get("/{person_id}/full-profile")
def full_profile(workspace_id: UUID, person_id: UUID, settings: SettingsDep, ctx: ViewCtx,
                 competition_id: UUID | None = None, season_id: UUID | None = None,
                 organisation_id: UUID | None = None) -> dict[str, Any]:
    """Everything for the Player Profile screen in one call: career + seasons + clubs + records +
    milestones + badges + honours (plus identity/photos via /profile). ``organisation_id`` scopes the
    career figures to one club (the ``clubs`` list is always complete, so the screen can offer the choice)."""
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return player_profile.full_profile(conn, workspace_id, person_id, competition_id=competition_id,
                                           season_id=season_id, organisation_id=organisation_id)


@router.get("/{person_id}/analysis")
def player_analysis(workspace_id: UUID, person_id: UUID, settings: SettingsDep, ctx: ViewCtx) -> dict[str, Any]:
    """Career analysis for the profile: performance splits (opposition/ground/grade/format), best batting &
    bowling, top partnerships, dismissal analysis and chart series — approved data, one engine, no copy."""
    from onestats.domain.records import player_analysis as pa
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return pa.player_analysis(conn, workspace_id, person_id)


@router.get("/{person_id}/profile.pdf")
def profile_pdf(workspace_id: UUID, person_id: UUID, settings: SettingsDep, ctx: ViewCtx,
                organisation_id: UUID | None = None) -> Response:
    """Professional player career-profile PDF (shared framework; same figures as on screen). Pass
    organisation_id to scope the figures to one club, matching the profile screen's club selector."""
    from onestats.reports import player_pdf
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        pdf = player_pdf.player_profile_pdf(conn, settings, workspace_id, person_id,
                                            organisation_id=organisation_id)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": 'inline; filename="player-profile.pdf"'})


@router.put("/{person_id}/profile")
def upsert_profile(workspace_id: UUID, person_id: UUID, body: ProfileUpsert, settings: SettingsDep, ctx: PCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _ids(profiles.upsert_profile(conn, workspace_id, str(ctx.user["id"]), person_id,
                                                **body.model_dump(exclude_none=True)))
        except ValueError as exc:
            raise _value_error(exc) from exc


@router.post("/{person_id}/numbers", status_code=status.HTTP_201_CREATED)
def add_number(workspace_id: UUID, person_id: UUID, body: NumberAdd, settings: SettingsDep, ctx: PCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            nid = profiles.add_number(conn, workspace_id, str(ctx.user["id"]), person_id,
                                      organisation_id=body.organisation_id, number=body.number,
                                      season_label=body.season_label, valid_from=body.valid_from,
                                      valid_to=body.valid_to, note=body.note)
        except ValueError as exc:
            raise _value_error(exc) from exc
        return {"number_id": str(nid)}


@router.post("/{person_id}/leadership", status_code=status.HTTP_201_CREATED)
def add_leadership(workspace_id: UUID, person_id: UUID, body: LeadershipAdd, settings: SettingsDep, ctx: PCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            lid = profiles.add_leadership(conn, workspace_id, str(ctx.user["id"]), person_id,
                                          organisation_id=body.organisation_id, role=body.role,
                                          team_id=body.team_id, season_label=body.season_label,
                                          valid_from=body.valid_from, valid_to=body.valid_to, note=body.note)
        except ValueError as exc:
            raise _value_error(exc) from exc
        return {"leadership_id": str(lid)}


@router.post("/{person_id}/recognition", status_code=status.HTTP_201_CREATED)
def add_recognition(workspace_id: UUID, person_id: UUID, body: RecognitionAdd, settings: SettingsDep, ctx: PCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            rid = profiles.add_recognition(conn, workspace_id, str(ctx.user["id"]), person_id,
                                           recognition_type=body.recognition_type, organisation_id=body.organisation_id,
                                           title=body.title, awarded_on=body.awarded_on,
                                           season_label=body.season_label, evidence=body.evidence, notes=body.notes)
        except ValueError as exc:
            raise _value_error(exc) from exc
        return {"recognition_id": str(rid)}


@router.delete("/{person_id}/numbers/{attr_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_number(workspace_id: UUID, person_id: UUID, attr_id: UUID, settings: SettingsDep, ctx: PCtx) -> None:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            profiles.delete_attribute(conn, workspace_id, str(ctx.user["id"]), person_id, "number", attr_id)
        except ValueError as exc:
            raise _value_error(exc) from exc


@router.delete("/{person_id}/leadership/{attr_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_leadership(workspace_id: UUID, person_id: UUID, attr_id: UUID, settings: SettingsDep, ctx: PCtx) -> None:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            profiles.delete_attribute(conn, workspace_id, str(ctx.user["id"]), person_id, "leadership", attr_id)
        except ValueError as exc:
            raise _value_error(exc) from exc


@router.delete("/{person_id}/recognition/{attr_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_recognition(workspace_id: UUID, person_id: UUID, attr_id: UUID, settings: SettingsDep, ctx: PCtx) -> None:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            profiles.delete_attribute(conn, workspace_id, str(ctx.user["id"]), person_id, "recognition", attr_id)
        except ValueError as exc:
            raise _value_error(exc) from exc


@router.get("/{person_id}/photos")
def list_photos(workspace_id: UUID, person_id: UUID, settings: SettingsDep, ctx: PCtx) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return [_ids(p) for p in profiles.list_photos(conn, person_id)]


@router.post("/{person_id}/photos", status_code=status.HTTP_201_CREATED)
async def upload_photo(
    workspace_id: UUID, person_id: UUID, settings: SettingsDep, ctx: PCtx, file: UploadFile,
    is_primary: bool = False, caption: str | None = None, public_visible: bool = False,
) -> dict[str, Any]:
    raw = await file.read()
    try:
        stored = photos.store_photo(settings, workspace_id, raw, file.content_type or "")
    except images.ImageError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            pid = profiles.register_photo(
                conn, workspace_id, str(ctx.user["id"]), person_id, media_key=str(stored["media_key"]),
                is_primary=is_primary, caption=caption, public_visible=public_visible,
                width=int(stored["width"]), height=int(stored["height"]), format=str(stored["format"]),
            )
        except ValueError as exc:
            # Roll back the stored file if the metadata insert fails.
            photos.remove_photo(settings, workspace_id, str(stored["media_key"]))
            raise _value_error(exc) from exc
        return {"photo_id": str(pid), **{k: stored[k] for k in ("media_key", "width", "height", "format")}}


@router.get("/photos/{photo_id}/file")
def get_photo_file(workspace_id: UUID, photo_id: UUID, settings: SettingsDep, ctx: PCtx) -> FileResponse:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        photo = profiles.get_photo(conn, photo_id)
    if photo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "photo_not_found")
    path = photos.photo_path(settings, workspace_id, photo["media_key"])
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "photo_file_missing")
    return FileResponse(str(path))


@router.delete("/photos/{photo_id}")
def delete_photo(workspace_id: UUID, photo_id: UUID, settings: SettingsDep, ctx: PCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            row = profiles.delete_photo(conn, workspace_id, str(ctx.user["id"]), photo_id)
        except ValueError as exc:
            raise _value_error(exc) from exc
        media_key = row["media_key"]
    photos.remove_photo(settings, workspace_id, media_key)
    return {"deleted": True}
