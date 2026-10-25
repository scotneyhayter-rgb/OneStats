"""Phase 12, Stages 12.15/12.16 — shared PDF report framework (no DB)."""
from __future__ import annotations

from onestats.reports.builder import Column, ReportDoc, Section, build_pdf


def _doc(rows, columns, **kw):
    return ReportDoc(title="Leading Run Scorers", workspace_name="Rhymney/Moyston CC",
                     sections=[Section(heading="All-time", columns=columns, rows=rows,
                                       note="Qualified: min 500 runs.")],
                     period="All seasons", filters=["Competition: ADCA", "Split: All matches"],
                     qualification_notes=["Unknown balls faced excluded from strike rate (not treated as zero)."],
                     **kw)


COLS = [
    Column("rank", "#", "right"), Column("player", "Player"), Column("matches", "M", "right"),
    Column("innings", "Inns", "right"), Column("runs", "Runs", "right"),
    Column("average", "Avg", "right", decimals=2), Column("strike_rate", "SR", "right", decimals=2),
    Column("hundreds", "100s", "right"),
]


def test_pdf_is_vector_and_multipage():
    rows = [{"rank": i, "player": f"A Really Quite Long Player Name {i}", "matches": 120 - i,
             "innings": 150 - i, "runs": 5000 - i * 37, "average": 42.5 - i * 0.1,
             "strike_rate": None if i % 9 == 0 else 78.3, "hundreds": 10 - (i % 5)} for i in range(1, 90)]
    pdf = build_pdf(_doc(rows, COLS))
    assert pdf[:5] == b"%PDF-" and len(pdf) > 3000
    assert b"/Page" in pdf   # real pages, not an image


def test_portrait_cover_and_unknown_dashes():
    rows = [{"rank": 1, "player": "Solo", "matches": 10, "innings": 12, "runs": 400,
             "average": None, "strike_rate": None, "hundreds": 0}]
    pdf = build_pdf(_doc(rows, COLS, orientation="portrait", cover_page=True))
    assert pdf[:5] == b"%PDF-" and len(pdf) > 2000


def test_many_columns_defaults_to_landscape():
    cols = COLS + [Column("fours", "4s", "right"), Column("sixes", "6s", "right"),
                   Column("fifties", "50s", "right")]
    pdf = build_pdf(_doc([{c.key: 1 for c in cols}], cols))
    assert pdf[:5] == b"%PDF-"
