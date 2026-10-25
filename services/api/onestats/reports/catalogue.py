"""Report catalogue (Phase 12, Stages 12.13/12.15).

Maps report keys to the one statistics engine and the shared PDF builder, so every report exports to a
branded, print-ready PDF whose figures match the on-screen report exactly. Workspace name + logo + the
applied filters are carried into the PDF header.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.core.config import Settings
from onestats.domain import branding, logos
from onestats.domain.stats import competition_points, engine
from onestats.reports.builder import Column, ReportDoc, Section, build_pdf

# report key -> (title, [columns], data function(conn, filters) -> rows). Each row is enriched with rank.
_C = Column

REPORTS: dict[str, dict[str, Any]] = {
    "batting": {
        "title": "Batting — Leading Run Scorers",
        "columns": [_C("rank", "#", "right"), _C("player", "Player"), _C("matches", "M", "right"),
                    _C("innings", "Inns", "right"), _C("not_outs", "NO", "right"), _C("runs", "Runs", "right"),
                    _C("highest_score", "HS", "right"), _C("average", "Avg", "right", 2),
                    _C("strike_rate", "SR", "right", 2), _C("fifties", "50s", "right"),
                    _C("hundreds", "100s", "right"), _C("ducks", "0s", "right")],
        "fn": lambda conn, f, **kw: engine.batting_leaders(conn, f, order_by=kw.get("order_by", "runs"),
                                                           min_runs=kw.get("min_runs")),
    },
    "bowling": {
        "title": "Bowling — Leading Wicket Takers",
        "columns": [_C("rank", "#", "right"), _C("player", "Player"), _C("matches", "M", "right"),
                    _C("overs", "Overs", "right", 1), _C("maidens", "Mdns", "right"), _C("runs", "Runs", "right"),
                    _C("wickets", "Wkts", "right"), _C("average", "Avg", "right", 2),
                    _C("economy", "Econ", "right", 2), _C("strike_rate", "SR", "right", 2),
                    _C("five_wkt_innings", "5wi", "right")],
        "fn": lambda conn, f, **kw: engine.bowling_leaders(conn, f, order_by=kw.get("order_by", "wickets"),
                                                           over_length=kw.get("over_length", 6),
                                                           min_wickets=kw.get("min_wickets")),
    },
    "fielding": {
        "title": "Fielding & Wicketkeeping",
        "columns": [_C("rank", "#", "right"), _C("player", "Player"), _C("matches", "M", "right"),
                    _C("catches", "Ct", "right"), _C("keeper_catches", "Ct (wk)", "right"),
                    _C("stumpings", "St", "right"), _C("run_outs", "RO", "right"),
                    _C("keeper_dismissals", "WK Dis", "right")],
        "fn": lambda conn, f, **kw: engine.fielding_leaders(conn, f, order_by=kw.get("order_by", "catches")),
    },
    "captaincy": {
        "title": "Captaincy Records",
        "columns": [_C("rank", "#", "right"), _C("player", "Captain"), _C("captained", "M", "right"),
                    _C("wins", "W", "right"), _C("losses", "L", "right"), _C("draws", "D", "right"),
                    _C("ties", "T", "right"), _C("win_pct", "Win %", "right", 1),
                    _C("gf_captained", "GF", "right"), _C("gf_wins", "GF W", "right")],
        "fn": lambda conn, f, **kw: engine.captaincy_leaders(conn, f, order_by=kw.get("order_by", "captained"),
                                                            min_eligible=kw.get("min_eligible", 20)),
    },
    "participation": {
        "title": "Player Appearances",
        "columns": [_C("rank", "#", "right"), _C("player", "Player"), _C("matches", "M", "right"),
                    _C("wins", "W", "right"), _C("losses", "L", "right")],
        "fn": lambda conn, f, **kw: engine.participation_leaders(conn, f, order_by=kw.get("order_by", "matches")),
    },
    "teams": {
        "title": "Team Records",
        "columns": [_C("rank", "#", "right"), _C("team", "Team"), _C("played", "P", "right"),
                    _C("wins", "W", "right"), _C("losses", "L", "right"), _C("draws", "D", "right"),
                    _C("ties", "T", "right"), _C("win_pct", "Win %", "right", 1)],
        "fn": lambda conn, f, **kw: engine.team_records(conn, f, order_by=kw.get("order_by", "wins")),
    },
}


def _name_map(conn: Connection, workspace_id: UUID) -> Callable[[dict[str, Any]], None]:
    people = {str(r["id"]): r["display_name"] for r in conn.execute(
        text("SELECT id, display_name FROM person WHERE workspace_id = :w"), {"w": workspace_id}).mappings()}
    teams = {str(r["id"]): r["name"] for r in conn.execute(
        text("SELECT id, name FROM team WHERE workspace_id = :w"), {"w": workspace_id}).mappings()}

    def enrich(rows: list[dict[str, Any]]) -> None:
        for i, r in enumerate(rows, 1):
            r["rank"] = i
            if "subject_id" in r:
                r["player"] = people.get(r["subject_id"], "Unknown")
                r["team"] = teams.get(r["subject_id"], r.get("player", "Unknown"))
    return enrich


def report_rows(conn: Connection, workspace_id: UUID, report: str, filters: dict[str, Any], **kw: Any) -> dict[str, Any]:
    if report not in REPORTS:
        raise ValueError("unknown_report")
    spec = REPORTS[report]
    rows = spec["fn"](conn, filters, **kw)
    _name_map(conn, workspace_id)(rows)
    return {"report": report, "title": spec["title"],
            "columns": [{"key": c.key, "label": c.label, "align": c.align, "decimals": c.decimals}
                        for c in spec["columns"]],
            "rows": rows}


def _branding(conn: Connection, settings: Settings, workspace_id: UUID) -> tuple[str, str | None, str | None]:
    ws = conn.execute(text("SELECT name FROM workspace WHERE id = :w"), {"w": workspace_id}).mappings().first()
    name = ws["name"] if ws else "OneStats"
    b = branding.get_branding(conn, workspace_id)
    logo_ref = (b or {}).get("logo_ref")
    logo_path = None
    if logo_ref:
        p = logos.logo_path(settings, workspace_id, logo_ref)
        logo_path = str(p) if p else None
    brand_hex = ((b or {}).get("colours") or {}).get("primary") if isinstance(b, dict) else None
    return name, logo_path, brand_hex


def report_pdf(conn: Connection, settings: Settings, workspace_id: UUID, report: str, filters: dict[str, Any],
               *, period: str | None = None, filter_labels: list[str] | None = None, cover: bool = False,
               **kw: Any) -> bytes:
    if report not in REPORTS:
        raise ValueError("unknown_report")
    spec = REPORTS[report]
    data = report_rows(conn, workspace_id, report, filters, **kw)
    name, logo_path, brand_hex = _branding(conn, settings, workspace_id)
    notes = [("Official statistics from approved scorecards only. Unknown values are not treated as zero; "
              "strike/economy rates use recorded balls only.")]
    doc = ReportDoc(title=spec["title"], workspace_name=name, period=period,
                    filters=filter_labels or [], qualification_notes=notes, cover_page=cover,
                    logo_path=logo_path, brand_hex=brand_hex,
                    sections=[Section(heading=spec["title"], columns=spec["columns"], rows=data["rows"])])
    return build_pdf(doc)


def ladder_pdf(conn: Connection, settings: Settings, workspace_id: UUID, competition_id: UUID,
               *, season_id: UUID | None = None, grade_id: UUID | None = None) -> bytes:
    lad = competition_points.ladder(conn, workspace_id, competition_id=competition_id, season_id=season_id,
                                    grade_id=grade_id)
    teams = {str(r["id"]): r["name"] for r in conn.execute(
        text("SELECT id, name FROM team WHERE workspace_id = :w"), {"w": workspace_id}).mappings()}
    for s in lad["standings"]:
        s["team"] = teams.get(s["team_id"], "Unknown")
    name, logo_path, brand_hex = _branding(conn, settings, workspace_id)
    cols = [Column("position", "#", "right"), Column("team", "Team"), Column("played", "P", "right"),
            Column("wins", "W", "right"), Column("losses", "L", "right"), Column("draws", "D", "right"),
            Column("ties", "T", "right"), Column("no_results", "NR", "right"),
            Column("bonus", "Bonus", "right", 1), Column("points", "Points", "right", 1)]
    doc = ReportDoc(title="Competition Ladder", workspace_name=name, logo_path=logo_path, brand_hex=brand_hex,
                    qualification_notes=[lad["note"]],
                    sections=[Section(heading="Standings", columns=cols, rows=lad["standings"])])
    return build_pdf(doc)
