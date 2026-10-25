"""Shared PDF report builder (Phase 12, Stages 12.15/12.16).

Produces print-ready A4 PDFs with vector text tables (never screenshots): workspace logo + club name,
report title, reporting period, applied filters, generation date, professional headers/footers, page
numbering ("Page X of Y"), table headers repeated on every page, right-aligned numeric columns with
consistent decimal precision, sensible margins, long names wrapped (never clipped), qualification notes,
and an optional cover page for substantial documents. One builder for all reports.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

_BRAND = colors.HexColor("#0b5e3b")       # OneStats cricket green (overridden by workspace colour if given)
_HEADER_BG = colors.HexColor("#0b5e3b")
_ALT_ROW = colors.HexColor("#f3f6f4")


@dataclass
class Column:
    key: str
    label: str
    align: str = "left"          # left | right | center
    decimals: int | None = None  # None = as-is; 0/1/2 = fixed decimals for numbers
    width: float | None = None   # mm


@dataclass
class Section:
    heading: str
    columns: list[Column]
    rows: list[dict[str, Any]]
    note: str | None = None


@dataclass
class ReportDoc:
    title: str
    workspace_name: str
    sections: list[Section]
    subtitle: str | None = None
    period: str | None = None
    filters: list[str] = field(default_factory=list)
    qualification_notes: list[str] = field(default_factory=list)
    orientation: str = "auto"        # portrait | landscape | auto
    cover_page: bool = False
    logo_path: str | None = None
    brand_hex: str | None = None


def _fmt(value: Any, col: Column) -> str:
    if value is None:
        return "—"
    if col.decimals is not None and isinstance(value, (int, float)):
        return f"{value:.{col.decimals}f}"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


class _NumberedCanvas(canvas.Canvas):
    """Two-pass canvas so the footer can print 'Page X of Y'."""

    def __init__(self, *a: Any, footer_cb=None, **k: Any) -> None:
        super().__init__(*a, **k)
        self._saved: list[dict[str, Any]] = []
        self._footer_cb = footer_cb

    def showPage(self) -> None:
        self._saved.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        total = len(self._saved)
        for state in self._saved:
            self.__dict__.update(state)
            if self._footer_cb:
                self._footer_cb(self, self._pageNumber, total)
            super().showPage()
        super().save()


def build_pdf(doc: ReportDoc) -> bytes:
    wide = max((len(s.columns) for s in doc.sections), default=0) > 6
    orient = doc.orientation if doc.orientation in ("portrait", "landscape") else ("landscape" if wide else "portrait")
    pagesize = landscape(A4) if orient == "landscape" else A4
    brand = colors.HexColor(doc.brand_hex) if doc.brand_hex else _BRAND

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("t", parent=styles["Title"], fontSize=16, textColor=brand, spaceAfter=2)
    h_style = ParagraphStyle("h", parent=styles["Heading2"], fontSize=12, textColor=brand, spaceBefore=8, spaceAfter=4)
    cell = ParagraphStyle("cell", parent=styles["BodyText"], fontSize=8.5, leading=10)
    cell_r = ParagraphStyle("cellr", parent=cell, alignment=TA_RIGHT)
    cell_c = ParagraphStyle("cellc", parent=cell, alignment=TA_CENTER)
    head_cell = ParagraphStyle("hc", parent=cell, textColor=colors.white, fontName="Helvetica-Bold")
    head_cell_r = ParagraphStyle("hcr", parent=head_cell, alignment=TA_RIGHT)
    small = ParagraphStyle("small", parent=styles["BodyText"], fontSize=8, textColor=colors.grey)

    margin = 15 * mm
    width = pagesize[0] - 2 * margin
    gen = datetime.now(UTC).strftime("%d %b %Y %H:%M UTC")

    def _header(c: canvas.Canvas, d: Any) -> None:
        c.saveState()
        y = pagesize[1] - margin + 4 * mm
        if doc.logo_path:
            try:
                c.drawImage(doc.logo_path, margin, y - 6 * mm, width=12 * mm, height=12 * mm,
                            preserveAspectRatio=True, mask="auto")
            except Exception:  # noqa: BLE001, S110 - a bad/missing logo must never break the report
                pass
        c.setFillColor(brand)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(margin + (14 * mm if doc.logo_path else 0), y - 2 * mm, doc.workspace_name)
        c.setFillColor(colors.grey)
        c.setFont("Helvetica", 8)
        c.drawRightString(pagesize[0] - margin, y - 2 * mm, doc.title)
        c.setStrokeColor(brand)
        c.line(margin, y - 4 * mm, pagesize[0] - margin, y - 4 * mm)
        c.restoreState()

    def _footer(c: canvas.Canvas, page: int, total: int) -> None:
        c.saveState()
        c.setFont("Helvetica", 7.5)
        c.setFillColor(colors.grey)
        c.drawString(margin, 10 * mm, f"Generated {gen} · OneStats")
        c.drawRightString(pagesize[0] - margin, 10 * mm, f"Page {page} of {total}")
        c.restoreState()

    buf = io.BytesIO()
    frame = Frame(margin, 15 * mm, width, pagesize[1] - 2 * margin - 2 * mm, id="body")
    template = PageTemplate(id="main", frames=[frame], onPage=_header)
    bdoc = BaseDocTemplate(buf, pagesize=pagesize, pageTemplates=[template],
                           leftMargin=margin, rightMargin=margin, topMargin=margin, bottomMargin=20 * mm,
                           title=doc.title, author="OneStats")

    flow: list[Any] = []
    if doc.cover_page:
        flow += [Spacer(1, 60 * mm), Paragraph(doc.workspace_name, title_style),
                 Paragraph(doc.title, ParagraphStyle("ct", parent=title_style, fontSize=22))]
        if doc.subtitle:
            flow.append(Paragraph(doc.subtitle, h_style))
        if doc.period:
            flow.append(Paragraph(f"Reporting period: {doc.period}", small))
        flow.append(Paragraph(f"Generated {gen}", small))
        flow.append(PageBreak())

    flow.append(Paragraph(doc.title, title_style))
    if doc.subtitle:
        flow.append(Paragraph(doc.subtitle, h_style))
    meta_bits = []
    if doc.period:
        meta_bits.append(f"<b>Period:</b> {doc.period}")
    if doc.filters:
        meta_bits.append("<b>Filters:</b> " + "; ".join(doc.filters))
    if meta_bits:
        flow.append(Paragraph(" &nbsp;·&nbsp; ".join(meta_bits), small))
    flow.append(Spacer(1, 3 * mm))

    for section in doc.sections:
        # Don't repeat the document title as a section heading (single-section reports would show it twice).
        if section.heading and section.heading != doc.title:
            flow.append(Paragraph(section.heading, h_style))
        header_row = [Paragraph(c.label, head_cell_r if c.align == "right" else head_cell) for c in section.columns]
        data = [header_row]
        for r in section.rows:
            row = []
            for c in section.columns:
                style = cell_r if c.align == "right" else (cell_c if c.align == "center" else cell)
                row.append(Paragraph(_fmt(r.get(c.key), c), style))
            data.append(row)
        col_widths = None
        if any(c.width for c in section.columns):
            col_widths = [(c.width * mm) if c.width else (width / len(section.columns)) for c in section.columns]
        t = Table(data, repeatRows=1, colWidths=col_widths, hAlign="LEFT")
        style = [
            ("BACKGROUND", (0, 0), (-1, 0), _HEADER_BG),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _ALT_ROW]),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#d7ded9")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]
        t.setStyle(TableStyle(style))
        flow.append(t)
        if section.note:
            flow.append(Paragraph(section.note, small))
        flow.append(Spacer(1, 4 * mm))

    if doc.qualification_notes:
        flow.append(Spacer(1, 2 * mm))
        flow.append(Paragraph("<b>Notes & qualifications</b>", small))
        for n in doc.qualification_notes:
            flow.append(Paragraph(f"• {n}", small))

    bdoc.build(flow, canvasmaker=lambda *a, **k: _NumberedCanvas(*a, footer_cb=_footer, **k))
    return buf.getvalue()
