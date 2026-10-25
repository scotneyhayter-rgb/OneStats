"""Records reports & the Club Record Book (Phase 13, Stages 13.16/13.17).

Uses the ONE shared PDF framework (no separate exporter). Assembles a professional, multi-section record
publication — all-time record holders, seasonal leaders and Life Members — with a cover page and page
numbering. Includes honest qualifications where historical coverage is incomplete; never implies the
book is complete when records are known to be missing.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.core.config import Settings
from onestats.domain import branding, logos
from onestats.domain.records import honours, records
from onestats.reports.builder import Column, ReportDoc, Section, build_pdf

ALL_SECTIONS = ("all_time", "seasonal", "life_members")


def _brand(conn: Connection, settings: Settings, workspace_id: UUID) -> tuple[str, str | None, str | None]:
    ws = conn.execute(text("SELECT name FROM workspace WHERE id = :w"), {"w": workspace_id}).mappings().first()
    name = ws["name"] if ws else "OneStats"
    b = branding.get_branding(conn, workspace_id)
    ref = (b or {}).get("logo_ref")
    path = str(logos.logo_path(settings, workspace_id, ref)) if ref and logos.logo_path(settings, workspace_id, ref) else None
    hexc = ((b or {}).get("colours") or {}).get("primary") if isinstance(b, dict) else None
    return name, path, hexc


def record_book_pdf(conn: Connection, settings: Settings, workspace_id: UUID, *,
                    sections: list[str] | None = None, filters: dict[str, Any] | None = None) -> bytes:
    want = sections or list(ALL_SECTIONS)
    f = {"workspace_id": workspace_id, **(filters or {})}
    name, logo_path, hexc = _brand(conn, settings, workspace_id)
    doc_sections: list[Section] = []
    incomplete_note = False

    if "all_time" in want:
        rec = records.all_time_records(conn, workspace_id, f, top=10)
        for data in rec.values():
            ranking = data.get("ranking") or []
            if not ranking:
                continue
            if isinstance(ranking[0], dict) and "player" in ranking[0]:
                rows = [{"rank": r.get("rank", i + 1), "name": r.get("player", "Unknown"), "value": r.get("value")}
                        for i, r in enumerate(ranking)]
            else:  # partnerships ranking
                rows = [{"rank": i + 1, "name": f"{r.get('batter1', '?')} & {r.get('batter2', '?')}",
                         "value": r.get("runs")} for i, r in enumerate(ranking)]
            if any(isinstance(r, dict) and r.get("known_minimum") for r in [data.get("holder") or {}]):
                incomplete_note = True
            doc_sections.append(Section(
                heading=data["title"],
                columns=[Column("rank", "#", "right"), Column("name", "Holder"), Column("value", "", "right")],
                rows=rows))

    if "seasonal" in want:
        seasons = records.seasonal_leaders(conn, workspace_id)
        rows = []
        for s in seasons:
            rs = s.get("leading_run_scorer")
            wk = s.get("leading_wicket_taker")
            rows.append({"season": s["label"],
                         "runs": f"{rs['player']} ({rs['value']})" if rs else "—",
                         "wickets": f"{wk['player']} ({wk['value']})" if wk else "—"})
        if rows:
            doc_sections.append(Section(heading="Seasonal Leaders",
                                        columns=[Column("season", "Season"), Column("runs", "Leading Run Scorer"),
                                                 Column("wickets", "Leading Wicket Taker")], rows=rows))

    if "life_members" in want:
        lm = [h for h in honours.list_honours(conn, workspace_id)
              if h["honour_type"] in ("life_member", "honorary_member")]
        names = {str(r["id"]): r["display_name"] for r in conn.execute(
            text("SELECT id, display_name FROM person WHERE workspace_id = :w"), {"w": workspace_id}).mappings()}
        if lm:
            doc_sections.append(Section(
                heading="Life Members & Honorary Members",
                columns=[Column("name", "Member"), Column("title", "Recognition"), Column("season", "Season")],
                rows=[{"name": names.get(str(h["person_id"]), "—") if h["person_id"] else "—",
                       "title": h["title"],
                       "season": h["awarded_season"] or (h["awarded_date"].isoformat() if h["awarded_date"] else "—")}
                      for h in lm]))

    notes = [("Official records from approved scorecards only. Unknown values are not treated as zero; "
              "ties are preserved.")]
    if incomplete_note:
        notes.append("Some totals are known-minimums (incomplete historical data) — flagged, not confirmed exact.")

    doc = ReportDoc(title="Club Record Book", subtitle=name, workspace_name=name, logo_path=logo_path,
                    brand_hex=hexc, cover_page=True, qualification_notes=notes,
                    sections=doc_sections or [Section(heading="No records yet",
                                                      columns=[Column("x", " ")], rows=[])])
    return build_pdf(doc)
