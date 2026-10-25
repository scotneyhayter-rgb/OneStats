"""Generic Excel (.xlsx) adapter — Phase 8, Stage 8.4.

Reads a match-summary worksheet (header row + one row per match) and hands the rows to the shared
tabular builder. Only the first worksheet is read; blank cells are unknown (``None``), never zero.
"""
from __future__ import annotations

import io
from typing import Any

from onestats.domain.importing.adapter import SourceAdapter, register_adapter
from onestats.domain.importing.model import CanonicalDataset
from onestats.domain.importing.tabular import build_match_summary

_XLSX_MAGIC = b"PK\x03\x04"   # xlsx is a zip container


class ExcelScorecardAdapter(SourceAdapter):
    format_id = "excel_scorecard"
    display_name = "Excel match summary (.xlsx)"
    capabilities = frozenset({"matches"})

    def detect(self, sample: bytes | str, filename: str | None = None) -> float:
        name = (filename or "").lower()
        if name.endswith((".xlsx", ".xlsm")):
            return 0.85
        # a bare zip header is ambiguous (xlsx/docx/pptx all are zips); only weak confidence
        if isinstance(sample, bytes) and sample[:4] == _XLSX_MAGIC:
            return 0.55
        return 0.0

    def parse(self, content: bytes | str, *, filename: str | None = None) -> list[dict[str, Any]]:
        from openpyxl import load_workbook
        if isinstance(content, str):
            content = content.encode("latin-1", errors="ignore")
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        ws = wb[wb.sheetnames[0]]
        rows_iter = ws.iter_rows(values_only=True)
        try:
            header = [str(c).strip() if c is not None else "" for c in next(rows_iter)]
        except StopIteration:
            return []
        out: list[dict[str, Any]] = []
        for row in rows_iter:
            if row is None or all(c is None for c in row):
                continue
            out.append({header[i]: row[i] for i in range(min(len(header), len(row)))})
        wb.close()
        return out

    def normalize(self, raw: list[dict[str, Any]], *, mapping: dict[str, Any] | None = None) -> CanonicalDataset:
        return build_match_summary(raw, source_system=self.format_id, overrides=mapping)


register_adapter(ExcelScorecardAdapter())
