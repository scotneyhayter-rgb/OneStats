"""Professional player profile PDF (Phase 13 — player profiles, §25).

Uses the ONE shared PDF framework (no separate exporter; no screenshots). Produces a full career profile
— cover page, career overview, season-by-season, records held, milestones and awards — with workspace
branding. Figures come from the player-profile aggregation (the one engine), so the PDF and the screen
agree. Private personal details are not exported.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.engine import Connection

from onestats.core.config import Settings
from onestats.domain import people
from onestats.domain.records import player_profile
from onestats.reports.builder import Column, ReportDoc, Section, build_pdf
from onestats.reports.record_book import _brand


def player_profile_pdf(conn: Connection, settings: Settings, workspace_id: UUID, person_id: UUID) -> bytes:
    person = people.detail(conn, person_id, include_protected=False)
    name = (person or {}).get("display_name") or "Player"
    prof = player_profile.full_profile(conn, workspace_id, person_id)
    ws_name, logo_path, hexc = _brand(conn, settings, workspace_id)
    c = prof["career"]
    bat, bowl, field, capt = c["batting"], c["bowling"], c["fielding"], c["captaincy"]

    sections: list[Section] = []

    # career summary (a compact key-stats table)
    summary_rows = [
        {"stat": "Matches", "value": c["matches"]},
        {"stat": "Runs", "value": bat.get("runs")},
        {"stat": "Batting average", "value": bat.get("average")},
        {"stat": "Highest score", "value": bat.get("highest_score")},
        {"stat": "Hundreds / Fifties", "value": f"{bat.get('hundreds', 0)} / {bat.get('fifties', 0)}"},
        {"stat": "Wickets", "value": bowl.get("wickets")},
        {"stat": "Bowling average", "value": bowl.get("average")},
        {"stat": "Best bowling (match)", "value": bowl.get("best_match_wickets")},
        {"stat": "Catches / Stumpings / Run outs",
         "value": f"{field.get('catches', 0)} / {field.get('stumpings', 0)} / {field.get('run_outs', 0)}"},
        {"stat": "Matches captained", "value": capt.get("captained")},
    ]
    sections.append(Section(heading="Career summary",
                            columns=[Column("stat", "Statistic"), Column("value", "", "right")],
                            rows=summary_rows))

    if prof["seasons"]:
        sections.append(Section(
            heading="Season by season",
            columns=[Column("label", "Season"), Column("matches", "M", "right"), Column("runs", "Runs", "right"),
                     Column("batting_average", "Bat Avg", "right", 2), Column("wickets", "Wkts", "right"),
                     Column("bowling_average", "Bowl Avg", "right", 2), Column("catches", "Ct", "right"),
                     Column("captained", "Capt", "right")],
            rows=prof["seasons"]))

    if prof["records"]:
        sections.append(Section(heading="Records held",
                                columns=[Column("title", "Record"), Column("value", "", "right")],
                                rows=prof["records"]))

    achieved = []
    for data in prof["milestones"]["metrics"].values():
        for m in data["milestones"]:
            if m["state"].startswith("achieved"):
                achieved.append({"milestone": f"{m['threshold']} {data['label'].lower()}",
                                 "state": m["state"].replace("_", " ")})
    if achieved:
        sections.append(Section(heading="Career milestones",
                                columns=[Column("milestone", "Milestone"), Column("state", "Status")],
                                rows=achieved))

    if prof["honours"]:
        sections.append(Section(
            heading="Awards & honours",
            columns=[Column("title", "Award"), Column("award_category", "Category"), Column("awarded_season", "Season")],
            rows=[{"title": h["title"], "award_category": h.get("award_category") or h["honour_type"].replace("_", " "),
                   "awarded_season": h.get("awarded_season") or "—"} for h in prof["honours"]]))

    doc = ReportDoc(title=f"{name} — Career Profile", subtitle=ws_name, workspace_name=ws_name,
                    logo_path=logo_path, brand_hex=hexc, cover_page=True,
                    qualification_notes=[("Official statistics from approved scorecards only; unknown "
                                          "values are never treated as zero. Private personal details are "
                                          "not included.")],
                    sections=sections or [Section(heading="No approved statistics yet",
                                                  columns=[Column("x", " ")], rows=[])])
    return build_pdf(doc)
