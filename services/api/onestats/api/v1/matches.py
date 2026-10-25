"""Match endpoints (Phase 6, Stage 1).

Workspace-scoped, gated by ``match.manage``, audited. Classification is explicit and never
derived from the round label; results use an explicit vocabulary; match-scope playing conditions
resolve through match → grade → season → competition. Scorecard body and statistics are later.
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
from onestats.domain import match_formats, match_sources, matches, results, seasons, validation

router = APIRouter(prefix="/workspaces/{workspace_id}/matches", tags=["matches"])

MatchCtx = Annotated[RequestContext, Depends(require_permission("match.manage"))]
ApproveCtx = Annotated[RequestContext, Depends(require_permission("scorecard.approve"))]

_VALUE_ERR_STATUS = {
    "match_not_found": status.HTTP_404_NOT_FOUND,
    "competition_not_found": status.HTTP_404_NOT_FOUND,
    "grade_not_found": status.HTTP_404_NOT_FOUND,
    "season_not_found": status.HTTP_404_NOT_FOUND,
    "venue_not_found": status.HTTP_404_NOT_FOUND,
    "team_not_found": status.HTTP_404_NOT_FOUND,
    "winner_not_in_match": status.HTTP_409_CONFLICT,
    "toss_winner_not_in_match": status.HTTP_409_CONFLICT,
    "invalid_toss_decision": status.HTTP_400_BAD_REQUEST,
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


class MatchCreate(BaseModel):
    competition_id: UUID | None = None
    grade_id: UUID | None = None
    season_id: UUID | None = None
    venue_id: UUID | None = None
    match_date: date | None = None
    date_precision: str = "exact"
    round: str | None = None
    matchtype: str | None = None
    format: str | None = None
    status: str = "draft"
    notes: str | None = None
    source_system: str | None = None
    source_ref: str | None = None


class MatchUpdate(BaseModel):
    competition_id: UUID | None = None
    grade_id: UUID | None = None
    season_id: UUID | None = None
    venue_id: UUID | None = None
    match_date: date | None = None
    date_precision: str | None = None
    round: str | None = None
    matchtype: str | None = None
    format: str | None = None
    status: str | None = None
    notes: str | None = None
    include_in_statistics: bool | None = None


class ClassificationSet(BaseModel):
    classification: str = Field(pattern="^(home_away|final|grand_final|other|unclassified)$")
    finals_stage: str | None = None
    verified: bool = False
    classification_ref_id: UUID | None = None


class ResultSet(BaseModel):
    result_type: str = Field(pattern="^(home_win|away_win|tie|draw|no_result|abandoned|washout|forfeit|unknown)$")
    won_by_team_id: UUID | None = None
    margin_runs: int | None = Field(default=None, ge=0)
    margin_wickets: int | None = Field(default=None, ge=0, le=10)
    result_raw: str | None = None
    # a result entered/edited in the UI is a 'manual' override by default (preserved from auto-calc)
    result_source: str = Field(default="manual", pattern="^(calculated|recorded|manual|unknown)$")
    result_override_reason: str | None = None


class TeamSet(BaseModel):
    team_id: UUID
    is_home: bool
    captain_person_id: UUID | None = None
    acting_captain_person_id: UUID | None = None
    wicketkeeper_person_id: UUID | None = None
    wicketkeeper2_person_id: UUID | None = None
    bonus_points: float | None = None


class TossSet(BaseModel):
    toss_winner_team_id: UUID | None = None
    toss_decision: str | None = Field(default=None, pattern="^(bat|field|no_toss|not_recorded|unknown)$")


@router.post("", status_code=status.HTTP_201_CREATED)
def create_match(workspace_id: UUID, body: MatchCreate, settings: SettingsDep, ctx: MatchCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            data = body.model_dump()
            # default the format from the workspace's nominated default when none is given (Phase 7.5)
            if not data.get("format"):
                data["format"] = match_formats.default_format_label(conn, workspace_id)
            mid = matches.create_match(conn, workspace_id, str(ctx.user["id"]), **data)
        except ValueError as exc:
            raise _value_error(exc) from exc
        _auto_season(conn, workspace_id, str(ctx.user["id"]), mid)  # Phase 7.4
        return _ids(matches.detail(conn, mid))


def _auto_season(conn: Any, workspace_id: UUID, actor: str, match_id: UUID) -> None:
    """Auto-assign the season from the competition's rule (non-blocking; preserves manual seasons)."""
    try:
        seasons.auto_assign_season(conn, workspace_id, actor, match_id)
    except ValueError:
        pass


@router.get("")
def list_matches(
    workspace_id: UUID, settings: SettingsDep, ctx: MatchCtx,
    competition_id: UUID | None = None, grade_id: UUID | None = None, season_id: UUID | None = None,
    venue_id: UUID | None = None, classification: str | None = None, status_: str | None = None,
    date_from: date | None = None, date_to: date | None = None,
) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return [_ids(m) for m in matches.list_matches(
            conn, competition_id=competition_id, grade_id=grade_id, season_id=season_id, venue_id=venue_id,
            classification=classification, status=status_, date_from=date_from, date_to=date_to)]


@router.get("/{match_id}")
def get_match(workspace_id: UUID, match_id: UUID, settings: SettingsDep, ctx: MatchCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        d = matches.detail(conn, match_id)
        if d is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "match_not_found")
        d["teams"] = [_ids(t) for t in d["teams"]]
        # Phase 7.3: the result calculated from the scorecard, and any recorded-vs-calculated conflict
        d["computed_result"] = _ids(results.compute_result(conn, match_id))
        d["result_warnings"] = results.result_warnings(conn, match_id)
        d["season_warnings"] = seasons.season_warnings(conn, match_id)  # Phase 7.4
        d["validation"] = validation.match_validation(conn, match_id)   # Phase 7.1
        return _ids(d)


@router.patch("/{match_id}")
def update_match(workspace_id: UUID, match_id: UUID, body: MatchUpdate, settings: SettingsDep, ctx: MatchCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            matches.update_match(conn, workspace_id, str(ctx.user["id"]), match_id,
                                 **body.model_dump(exclude_none=True))
        except ValueError as exc:
            raise _value_error(exc) from exc
        _auto_season(conn, workspace_id, str(ctx.user["id"]), match_id)  # re-assign if date/comp changed
        return _ids(matches.get_match(conn, match_id))  # refreshed (reflects any new season)


@router.post("/{match_id}/classification")
def set_classification(workspace_id: UUID, match_id: UUID, body: ClassificationSet, settings: SettingsDep, ctx: MatchCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _ids(matches.set_classification(
                conn, workspace_id, str(ctx.user["id"]), match_id, classification=body.classification,
                finals_stage=body.finals_stage, verified=body.verified, classification_ref_id=body.classification_ref_id))
        except ValueError as exc:
            raise _value_error(exc) from exc


@router.post("/{match_id}/result")
def set_result(workspace_id: UUID, match_id: UUID, body: ResultSet, settings: SettingsDep, ctx: MatchCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _ids(matches.set_result(
                conn, workspace_id, str(ctx.user["id"]), match_id, result_type=body.result_type,
                won_by_team_id=body.won_by_team_id, margin_runs=body.margin_runs,
                margin_wickets=body.margin_wickets, result_raw=body.result_raw,
                result_source=body.result_source, result_override_reason=body.result_override_reason))
        except ValueError as exc:
            raise _value_error(exc) from exc


class ApprovalReason(BaseModel):
    reason: str | None = None


def _approve_to(conn: Any, workspace_id: UUID, actor: str, match_id: UUID, *, status_: str, reason: str | None):
    try:
        return _ids(matches.set_approval(conn, workspace_id, actor, match_id, status=status_, reason=reason))
    except ValueError as exc:
        raise _value_error(exc) from exc


# Scorecard approval workflow (Phase 7.1) — separate from the cricket match status. Submitting and
# reopening are editor actions (match.manage); approving and rejecting require scorecard.approve.
@router.post("/{match_id}/submit")
def submit_for_approval(workspace_id: UUID, match_id: UUID, body: ApprovalReason, settings: SettingsDep, ctx: MatchCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return _approve_to(conn, workspace_id, str(ctx.user["id"]), match_id, status_="awaiting_approval", reason=body.reason)


@router.post("/{match_id}/reopen")
def reopen_scorecard(workspace_id: UUID, match_id: UUID, body: ApprovalReason, settings: SettingsDep, ctx: MatchCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return _approve_to(conn, workspace_id, str(ctx.user["id"]), match_id, status_="draft", reason=body.reason)


@router.post("/{match_id}/approve")
def approve_scorecard(workspace_id: UUID, match_id: UUID, body: ApprovalReason, settings: SettingsDep, ctx: ApproveCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return _approve_to(conn, workspace_id, str(ctx.user["id"]), match_id, status_="approved", reason=body.reason)


@router.post("/{match_id}/reject")
def reject_scorecard(workspace_id: UUID, match_id: UUID, body: ApprovalReason, settings: SettingsDep, ctx: ApproveCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return _approve_to(conn, workspace_id, str(ctx.user["id"]), match_id, status_="rejected", reason=body.reason)


@router.post("/{match_id}/teams", status_code=status.HTTP_201_CREATED)
def set_team(workspace_id: UUID, match_id: UUID, body: TeamSet, settings: SettingsDep, ctx: MatchCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _ids(matches.set_team(
                conn, workspace_id, str(ctx.user["id"]), match_id, team_id=body.team_id, is_home=body.is_home,
                captain_person_id=body.captain_person_id, acting_captain_person_id=body.acting_captain_person_id,
                wicketkeeper_person_id=body.wicketkeeper_person_id, wicketkeeper2_person_id=body.wicketkeeper2_person_id,
                bonus_points=body.bonus_points))
        except ValueError as exc:
            raise _value_error(exc) from exc


@router.post("/{match_id}/toss")
def set_toss(workspace_id: UUID, match_id: UUID, body: TossSet, settings: SettingsDep, ctx: MatchCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _ids(matches.set_toss(
                conn, workspace_id, str(ctx.user["id"]), match_id,
                toss_winner_team_id=body.toss_winner_team_id, toss_decision=body.toss_decision))
        except ValueError as exc:
            raise _value_error(exc) from exc


@router.get("/{match_id}/conditions")
def effective_conditions(workspace_id: UUID, match_id: UUID, settings: SettingsDep, ctx: MatchCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return matches.effective_conditions(conn, match_id)
        except ValueError as exc:
            raise _value_error(exc) from exc


@router.get("/{match_id}/sources")
def match_source_provenance(workspace_id: UUID, match_id: UUID, settings: SettingsDep, ctx: MatchCtx) -> dict[str, Any]:
    """The sources that describe this match (import provenance, R1) and any fields on which they
    disagree — for tracing a scorecard back to its source(s) and reviewing conflicting accounts."""
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return {
            "sources": [_ids(s) for s in match_sources.list_match_sources(conn, match_id)],
            "conflicts": match_sources.source_conflicts(conn, match_id),
        }
