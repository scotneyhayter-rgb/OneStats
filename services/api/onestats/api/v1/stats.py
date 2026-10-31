"""Official statistics endpoints (Phase 7, Stage 7.8).

Read official player statistics from the approved-match ledger, and (admin) trigger a workspace
backfill that recomputes the ledger for every match. Workspace-scoped and audited. This is the
foundation the future statistics/records/milestones modules build on — not those modules themselves.
"""
from __future__ import annotations

from datetime import date
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import text

from onestats.api.deps import RequestContext, SettingsDep, require_permission
from onestats.db.session import get_engine
from onestats.db.workspace import workspace_transaction
from onestats.domain import data_quality, recalc
from onestats.domain.stats import (
    competition_points,
    engine,
    integrity,
    partnerships,
    reconciliation,
    records_detail,
    saved_reports,
)
from onestats.reports import catalogue

_SR_ERRORS = {
    "name_required": status.HTTP_400_BAD_REQUEST,
    "report_required": status.HTTP_400_BAD_REQUEST,
    "name_exists": status.HTTP_409_CONFLICT,
    "report_not_found": status.HTTP_404_NOT_FOUND,
    "not_owner": status.HTTP_403_FORBIDDEN,
}

router = APIRouter(prefix="/workspaces/{workspace_id}/stats", tags=["stats"])

ViewCtx = Annotated[RequestContext, Depends(require_permission("match.view"))]
AdminCtx = Annotated[RequestContext, Depends(require_permission("workspace.manage"))]


def _engine(settings):
    eng = get_engine(settings)
    if eng is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database not configured")
    return eng


@router.get("/people/{person_id}")
def official_person_stats(workspace_id: UUID, person_id: UUID, settings: SettingsDep, ctx: ViewCtx) -> dict[str, Any]:
    """Official career batting and bowling for a person, from approved scorecards only (merge-aware)."""
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return {
            "person_id": str(person_id),
            "batting": recalc.official_player_batting(conn, workspace_id, person_id),
            "bowling": recalc.official_player_bowling(conn, workspace_id, person_id),
        }


@router.post("/recalc")
def recalc_backfill(workspace_id: UUID, settings: SettingsDep, ctx: AdminCtx) -> dict[str, Any]:
    """Recompute the official-statistics ledger for every match in the workspace. Idempotent."""
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return recalc.backfill(conn, workspace_id, str(ctx.user["id"]))


def _filters(workspace_id: UUID, season_id: UUID | None, grade_id: UUID | None, competition_id: UUID | None,
             team_id: UUID | None, split: str | None, venue: str | None, format: str | None,
             date_from: date | None, date_to: date | None, organisation_id: UUID | None = None,
             opposition_team_id: UUID | None = None, opposition_organisation_id: UUID | None = None,
             venue_id: UUID | None = None) -> dict[str, Any]:
    return {"workspace_id": workspace_id, "season_id": season_id, "grade_id": grade_id,
            "competition_id": competition_id, "team_id": team_id, "organisation_id": organisation_id,
            "opposition_team_id": opposition_team_id, "opposition_organisation_id": opposition_organisation_id,
            "split": split, "venue": venue, "venue_id": venue_id, "format": format,
            "date_from": date_from, "date_to": date_to}


# One signature of shared report filters for every leaderboard (real filters over the one engine).
def _common(workspace_id: UUID, season_id: UUID | None = None, grade_id: UUID | None = None,
            competition_id: UUID | None = None, team_id: UUID | None = None, split: str | None = None,
            venue: str | None = None, format: str | None = None, date_from: date | None = None,
            date_to: date | None = None, order_by: str | None = None, limit: int = 100,
            organisation_id: UUID | None = None, opposition_team_id: UUID | None = None,
            opposition_organisation_id: UUID | None = None, venue_id: UUID | None = None) -> dict[str, Any]:
    return {"f": _filters(workspace_id, season_id, grade_id, competition_id, team_id, split, venue, format,
                          date_from, date_to, organisation_id, opposition_team_id, opposition_organisation_id,
                          venue_id),
            "order_by": order_by, "limit": limit}


@router.get("/primary-club")
def primary_club(workspace_id: UUID, settings: SettingsDep, ctx: ViewCtx) -> dict[str, Any]:
    """The workspace's main club (most player appearances) so the Stats screen can default to it, with
    "All clubs" as the alternative. Returns {} when there are no appearances yet."""
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return engine.primary_club(conn, workspace_id) or {}


@router.get("/batting")
def batting(workspace_id: UUID, settings: SettingsDep, ctx: ViewCtx, season_id: UUID | None = None,
            grade_id: UUID | None = None, competition_id: UUID | None = None, team_id: UUID | None = None,
            organisation_id: UUID | None = None, opposition_team_id: UUID | None = None,
            opposition_organisation_id: UUID | None = None, venue_id: UUID | None = None,
            split: str | None = None, venue: str | None = None, format: str | None = None,
            date_from: date | None = None, date_to: date | None = None, order_by: str = "runs",
            limit: int = 100, min_runs: int | None = None, min_innings: int | None = None) -> list[dict[str, Any]]:
    c = _common(workspace_id, season_id, grade_id, competition_id, team_id, split, venue, format, date_from, date_to,
                organisation_id=organisation_id, opposition_team_id=opposition_team_id,
                opposition_organisation_id=opposition_organisation_id, venue_id=venue_id)
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return engine.batting_leaders(conn, c["f"], order_by=order_by, limit=limit, min_runs=min_runs,
                                      min_innings=min_innings)


@router.get("/bowling")
def bowling(workspace_id: UUID, settings: SettingsDep, ctx: ViewCtx, season_id: UUID | None = None,
            grade_id: UUID | None = None, competition_id: UUID | None = None, team_id: UUID | None = None,
            organisation_id: UUID | None = None, opposition_team_id: UUID | None = None,
            opposition_organisation_id: UUID | None = None, venue_id: UUID | None = None,
            split: str | None = None, venue: str | None = None, format: str | None = None,
            date_from: date | None = None, date_to: date | None = None, order_by: str = "wickets",
            limit: int = 100, over_length: int = 6, min_wickets: int | None = None,
            min_innings: int | None = None) -> list[dict[str, Any]]:
    c = _common(workspace_id, season_id, grade_id, competition_id, team_id, split, venue, format, date_from, date_to,
                organisation_id=organisation_id, opposition_team_id=opposition_team_id,
                opposition_organisation_id=opposition_organisation_id, venue_id=venue_id)
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return engine.bowling_leaders(conn, c["f"], order_by=order_by, limit=limit, over_length=over_length,
                                      min_wickets=min_wickets, min_innings=min_innings)


@router.get("/fielding")
def fielding(workspace_id: UUID, settings: SettingsDep, ctx: ViewCtx, season_id: UUID | None = None,
             grade_id: UUID | None = None, competition_id: UUID | None = None, team_id: UUID | None = None,
             organisation_id: UUID | None = None, opposition_team_id: UUID | None = None,
             opposition_organisation_id: UUID | None = None, venue_id: UUID | None = None,
             split: str | None = None, venue: str | None = None, order_by: str = "catches",
             limit: int = 100) -> list[dict[str, Any]]:
    c = _common(workspace_id, season_id, grade_id, competition_id, team_id, split, venue, None, None, None,
                organisation_id=organisation_id, opposition_team_id=opposition_team_id,
                opposition_organisation_id=opposition_organisation_id, venue_id=venue_id)
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return engine.fielding_leaders(conn, c["f"], order_by=order_by, limit=limit)


@router.get("/captaincy")
def captaincy(workspace_id: UUID, settings: SettingsDep, ctx: ViewCtx, season_id: UUID | None = None,
              grade_id: UUID | None = None, competition_id: UUID | None = None, team_id: UUID | None = None,
              organisation_id: UUID | None = None, opposition_team_id: UUID | None = None,
              opposition_organisation_id: UUID | None = None, venue_id: UUID | None = None,
              split: str | None = None, order_by: str = "captained", limit: int = 100,
              min_eligible: int = 20) -> list[dict[str, Any]]:
    c = _common(workspace_id, season_id, grade_id, competition_id, team_id, split, None, None, None, None,
                organisation_id=organisation_id, opposition_team_id=opposition_team_id,
                opposition_organisation_id=opposition_organisation_id, venue_id=venue_id)
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return engine.captaincy_leaders(conn, c["f"], order_by=order_by, limit=limit, min_eligible=min_eligible)


@router.get("/participation")
def participation(workspace_id: UUID, settings: SettingsDep, ctx: ViewCtx, season_id: UUID | None = None,
                  grade_id: UUID | None = None, competition_id: UUID | None = None, team_id: UUID | None = None,
                  organisation_id: UUID | None = None, opposition_team_id: UUID | None = None,
                  opposition_organisation_id: UUID | None = None, venue_id: UUID | None = None,
                  split: str | None = None, order_by: str = "matches", limit: int = 100) -> list[dict[str, Any]]:
    c = _common(workspace_id, season_id, grade_id, competition_id, team_id, split, None, None, None, None,
                organisation_id=organisation_id, opposition_team_id=opposition_team_id,
                opposition_organisation_id=opposition_organisation_id, venue_id=venue_id)
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return engine.participation_leaders(conn, c["f"], order_by=order_by, limit=limit)


@router.get("/teams")
def teams(workspace_id: UUID, settings: SettingsDep, ctx: ViewCtx, season_id: UUID | None = None,
          grade_id: UUID | None = None, competition_id: UUID | None = None, split: str | None = None,
          order_by: str = "wins", limit: int = 100, opposition_team_id: UUID | None = None,
          opposition_organisation_id: UUID | None = None) -> list[dict[str, Any]]:
    c = _common(workspace_id, season_id, grade_id, competition_id, None, split, None, None, None, None,
                opposition_team_id=opposition_team_id, opposition_organisation_id=opposition_organisation_id)
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return engine.team_records(conn, c["f"], order_by=order_by, limit=limit)


@router.get("/partnerships/batting")
def batting_partnerships(workspace_id: UUID, settings: SettingsDep, ctx: ViewCtx, season_id: UUID | None = None,
                         grade_id: UUID | None = None, competition_id: UUID | None = None,
                         by_wicket: bool = False, limit: int = 50) -> list[dict[str, Any]]:
    f = _filters(workspace_id, season_id, grade_id, competition_id, None, None, None, None, None, None)
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return partnerships.batting_partnerships(conn, f, by_wicket=by_wicket, limit=limit)


@router.get("/partnerships/bowling-groups")
def bowling_groups(workspace_id: UUID, settings: SettingsDep, ctx: ViewCtx, size: int = 2,
                   season_id: UUID | None = None, grade_id: UUID | None = None,
                   competition_id: UUID | None = None, team_id: UUID | None = None, split: str | None = None,
                   limit: int = 50) -> dict[str, Any]:
    f = _filters(workspace_id, season_id, grade_id, competition_id, team_id, split, None, None, None, None)
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return partnerships.bowling_groups(conn, f, size=size, limit=limit)
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.get("/ladder")
def ladder(workspace_id: UUID, competition_id: UUID, settings: SettingsDep, ctx: ViewCtx,
           season_id: UUID | None = None, grade_id: UUID | None = None) -> dict[str, Any]:
    """Competition ladder using the configured points scheme (approved matches only)."""
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return competition_points.ladder(conn, workspace_id, competition_id=competition_id,
                                         season_id=season_id, grade_id=grade_id)


class SavedReportCreate(BaseModel):
    name: str
    report: str
    config: dict[str, Any] | None = None
    shared: bool = False


class SavedReportUpdate(BaseModel):
    name: str | None = None
    config: dict[str, Any] | None = None
    shared: bool | None = None


def _sr(d: dict[str, Any]) -> dict[str, Any]:
    return {k: (str(v) if isinstance(v, UUID) else v) for k, v in d.items()}


def _sr_err(exc: ValueError) -> HTTPException:
    return HTTPException(_SR_ERRORS.get(str(exc), status.HTTP_400_BAD_REQUEST), str(exc))


@router.get("/saved-reports")
def list_saved(workspace_id: UUID, settings: SettingsDep, ctx: ViewCtx) -> list[dict[str, Any]]:
    """The caller's saved reports plus any shared in the workspace."""
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return [_sr(r) for r in saved_reports.list_reports(conn, workspace_id, str(ctx.user["id"]))]


@router.post("/saved-reports", status_code=status.HTTP_201_CREATED)
def create_saved(workspace_id: UUID, body: SavedReportCreate, settings: SettingsDep, ctx: ViewCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _sr(saved_reports.create(conn, workspace_id, str(ctx.user["id"]), **body.model_dump()))
        except ValueError as exc:
            raise _sr_err(exc) from exc


@router.patch("/saved-reports/{report_id}")
def update_saved(workspace_id: UUID, report_id: UUID, body: SavedReportUpdate, settings: SettingsDep,
                 ctx: ViewCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _sr(saved_reports.update(conn, workspace_id, str(ctx.user["id"]), report_id,
                                           **body.model_dump(exclude_none=True)))
        except ValueError as exc:
            raise _sr_err(exc) from exc


@router.delete("/saved-reports/{report_id}")
def delete_saved(workspace_id: UUID, report_id: UUID, settings: SettingsDep, ctx: ViewCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return {"deleted": saved_reports.delete(conn, workspace_id, str(ctx.user["id"]), report_id)}
        except ValueError as exc:
            raise _sr_err(exc) from exc


@router.get("/reports")
def list_reports(workspace_id: UUID, settings: SettingsDep, ctx: ViewCtx) -> list[dict[str, Any]]:
    """The report base types (same engine behind each). See /catalogue for the full library."""
    return [{"report": k, "title": v["title"]} for k, v in catalogue.REPORTS.items()]


@router.get("/catalogue")
def report_catalogue(workspace_id: UUID, settings: SettingsDep, ctx: ViewCtx) -> dict[str, Any]:
    """The full, categorised Report Catalogue (every report uses the one engine; scope is a filter)."""
    return catalogue.catalogue_metadata()


@router.get("/formats")
def used_formats(workspace_id: UUID, settings: SettingsDep, ctx: ViewCtx) -> list[str]:
    """Match formats offered in the report Format filter: the workspace's ENABLED configured formats, plus
    any free-text format actually present on statistics-eligible matches (``match.format`` is free text), so
    the filter is both always visible and covers imported/custom values. De-duplicated, sorted."""
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        rows = conn.execute(
            text("SELECT label AS fmt FROM match_format WHERE workspace_id = :w AND enabled = true "
                 "UNION "
                 "SELECT DISTINCT format FROM match WHERE workspace_id = :w AND format IS NOT NULL "
                 "AND format <> '' AND approval_status IN ('approved','verified_partial') "
                 "AND include_in_statistics = true "
                 "ORDER BY fmt"),
            {"w": workspace_id}).all()
        return [r[0] for r in rows]


@router.get("/captaincy/compare")
def captaincy_compare(workspace_id: UUID, person_ids: str, settings: SettingsDep, ctx: ViewCtx) -> dict[str, Any]:
    """Side-by-side captaincy comparison for the selected captains (comma-separated person ids)."""
    try:
        ids = [UUID(x) for x in person_ids.split(",") if x.strip()]
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid_person_id") from exc
    if not ids:
        return {"captains": []}
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return {"captains": records_detail.captaincy_comparison(conn, workspace_id, ids)}


@router.get("/catalogue/index.pdf")
def catalogue_index(workspace_id: UUID, settings: SettingsDep, ctx: ViewCtx) -> Response:
    """A printable catalogue index: every report, grouped by category, with its description."""
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        pdf = catalogue.catalogue_index_pdf(conn, settings, workspace_id)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": 'inline; filename="report-catalogue.pdf"'})


@router.get("/reports/{report}")
def report_data(workspace_id: UUID, report: str, settings: SettingsDep, ctx: ViewCtx,
                season_id: UUID | None = None, grade_id: UUID | None = None, competition_id: UUID | None = None,
                team_id: UUID | None = None, organisation_id: UUID | None = None,
                opposition_team_id: UUID | None = None, opposition_organisation_id: UUID | None = None,
                venue_id: UUID | None = None,
                split: str | None = None, venue: str | None = None,
                format: str | None = None, order_by: str | None = None, min_runs: int | None = None,
                min_wickets: int | None = None, over_length: int | None = None,
                min_eligible: int | None = None, min_innings: int | None = None) -> dict[str, Any]:
    """On-screen report data (columns + rows) from the one engine — matches the PDF export exactly."""
    f = _filters(workspace_id, season_id, grade_id, competition_id, team_id, split, venue, format, None, None,
                 organisation_id, opposition_team_id, opposition_organisation_id, venue_id)
    kw = {k: v for k, v in {"order_by": order_by, "min_runs": min_runs, "min_wickets": min_wickets,
                            "over_length": over_length, "min_eligible": min_eligible,
                            "min_innings": min_innings}.items() if v is not None}
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return catalogue.report_rows(conn, workspace_id, report, f, **kw)
        except ValueError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.get("/reports/{report}/pdf")
def report_export(workspace_id: UUID, report: str, settings: SettingsDep, ctx: ViewCtx,
                  season_id: UUID | None = None, grade_id: UUID | None = None, competition_id: UUID | None = None,
                  team_id: UUID | None = None, organisation_id: UUID | None = None,
                  opposition_team_id: UUID | None = None, opposition_organisation_id: UUID | None = None,
                  venue_id: UUID | None = None, split: str | None = None,
                  venue: str | None = None, format: str | None = None, order_by: str | None = None,
                  min_runs: int | None = None, min_wickets: int | None = None, over_length: int | None = None,
                  min_eligible: int | None = None, min_innings: int | None = None,
                  period: str | None = None, cover: bool = False) -> Response:
    """Export the report as a print-ready, branded A4 PDF (same figures as on-screen)."""
    f = _filters(workspace_id, season_id, grade_id, competition_id, team_id, split, venue, format, None, None,
                 organisation_id, opposition_team_id, opposition_organisation_id, venue_id)
    kw = {k: v for k, v in {"order_by": order_by, "min_runs": min_runs, "min_wickets": min_wickets,
                            "over_length": over_length, "min_eligible": min_eligible,
                            "min_innings": min_innings}.items() if v is not None}
    labels = [lbl for lbl in (f"Split: {split}" if split else None, f"Venue: {venue}" if venue else None,
                              f"Format: {format}" if format else None) if lbl]
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            pdf = catalogue.report_pdf(conn, settings, workspace_id, report, f, period=period,
                                       filter_labels=labels, cover=cover, **kw)
        except ValueError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{report}.pdf"'})


@router.get("/reports/{report}/csv")
def report_csv_export(workspace_id: UUID, report: str, settings: SettingsDep, ctx: ViewCtx,
                      season_id: UUID | None = None, grade_id: UUID | None = None, competition_id: UUID | None = None,
                      team_id: UUID | None = None, organisation_id: UUID | None = None,
                      opposition_team_id: UUID | None = None, opposition_organisation_id: UUID | None = None,
                      venue_id: UUID | None = None, split: str | None = None, venue: str | None = None,
                      format: str | None = None, order_by: str | None = None, min_runs: int | None = None,
                      min_wickets: int | None = None, over_length: int | None = None,
                      min_eligible: int | None = None, min_innings: int | None = None) -> Response:
    """Export a tabular report as CSV (same columns/figures as the on-screen report)."""
    f = _filters(workspace_id, season_id, grade_id, competition_id, team_id, split, venue, format, None, None,
                 organisation_id, opposition_team_id, opposition_organisation_id, venue_id)
    kw = {k: v for k, v in {"order_by": order_by, "min_runs": min_runs, "min_wickets": min_wickets,
                            "over_length": over_length, "min_eligible": min_eligible,
                            "min_innings": min_innings}.items() if v is not None}
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            data = catalogue.report_csv(conn, workspace_id, report, f, **kw)
        except ValueError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return Response(content=data, media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{report}.csv"'})


@router.get("/ladder/pdf")
def ladder_export(workspace_id: UUID, competition_id: UUID, settings: SettingsDep, ctx: ViewCtx,
                  season_id: UUID | None = None, grade_id: UUID | None = None) -> Response:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        pdf = catalogue.ladder_pdf(conn, settings, workspace_id, competition_id, season_id=season_id, grade_id=grade_id)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": 'inline; filename="ladder.pdf"'})


@router.get("/integrity")
def data_integrity(workspace_id: UUID, settings: SettingsDep, ctx: ViewCtx) -> dict[str, Any]:
    """Data-integrity summary: reconciliation issues across approved matches + unknown-data counts."""
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return integrity.workspace_integrity(conn, workspace_id)


@router.get("/compare")
def compare_players(workspace_id: UUID, settings: SettingsDep, ctx: ViewCtx, player_ids: str,
                    season_id: UUID | None = None, grade_id: UUID | None = None, competition_id: UUID | None = None,
                    team_id: UUID | None = None, organisation_id: UUID | None = None,
                    opposition_organisation_id: UUID | None = None, venue_id: UUID | None = None,
                    split: str | None = None, venue: str | None = None, format: str | None = None,
                    over_length: int = 6) -> dict[str, Any]:
    """Side-by-side comparison of two or more players — batting, bowling, fielding and captaincy under the
    SAME filters, from the one engine (so every figure matches the individual reports). Order follows the
    requested ids; an unknown player is skipped."""
    ids = [p.strip() for p in player_ids.split(",") if p.strip()][:8]
    f = _filters(workspace_id, season_id, grade_id, competition_id, team_id, split, venue, format, None, None,
                 organisation_id, None, opposition_organisation_id, venue_id)
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        names = {str(r["id"]): r["display_name"] for r in conn.execute(
            text("SELECT id, display_name FROM person WHERE workspace_id = :w"), {"w": workspace_id}).mappings()}
        players = []
        for pid in ids:
            if pid not in names:
                continue
            players.append({
                "person_id": pid, "name": names[pid],
                "batting": engine.person_batting(conn, f, UUID(pid)),
                "bowling": engine.person_bowling(conn, f, UUID(pid), over_length=over_length),
                "fielding": engine.person_fielding(conn, f, UUID(pid)),
                "captaincy": engine.person_captaincy(conn, f, UUID(pid)),
            })
        return {"players": players}


@router.get("/data-quality")
def data_quality_scan(workspace_id: UUID, settings: SettingsDep, ctx: ViewCtx) -> dict[str, Any]:
    """Scorer-error checks over the entered scorecards (missing fielder/bowler, captain/keeper not set,
    a batter/bowler listed twice, …), each with the offending matches for drill-down. Read-only."""
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return data_quality.scan(conn, workspace_id)


@router.get("/matches/{match_id}/reconciliation")
def match_reconciliation(workspace_id: UUID, match_id: UUID, settings: SettingsDep, ctx: ViewCtx) -> dict[str, Any]:
    """Run-out reconciliation for a match's innings: recorded wickets vs dismissals, with a visible run
    outs count and warnings where the scorecard is incomplete (never an invented dismissal)."""
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return reconciliation.reconcile_match(conn, workspace_id, match_id)
