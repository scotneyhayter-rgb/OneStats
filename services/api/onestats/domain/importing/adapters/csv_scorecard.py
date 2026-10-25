"""Generic CSV adapter — Phase 8, Stage 8.3/8.4.

Imports a match-summary CSV (one row per match). Detection + CSV parsing only; the shared tabular
builder maps rows to the Canonical model, so CSV/Excel/JSON/XML all behave identically and column
names remain remappable in the wizard.
"""
from __future__ import annotations

import csv
import io
from typing import Any

from onestats.domain.importing.adapter import SourceAdapter, register_adapter
from onestats.domain.importing.model import CanonicalDataset
from onestats.domain.importing.tabular import SUMMARY_COLUMNS, build_match_summary


class CsvScorecardAdapter(SourceAdapter):
    format_id = "csv_scorecard"
    display_name = "CSV match summary"
    capabilities = frozenset({"matches"})

    def detect(self, sample: bytes | str, filename: str | None = None) -> float:
        text = sample.decode("utf-8-sig", errors="ignore") if isinstance(sample, bytes) else sample
        header = text.splitlines()[0].lower() if text.strip() else ""
        if "," not in header:
            return 0.0
        cols = {c.strip().strip('"') for c in header.split(",")}
        hits = len(cols & SUMMARY_COLUMNS)
        score = 0.3 if filename and filename.lower().endswith(".csv") else 0.0
        score += min(hits * 0.2, 0.6)
        return score if hits >= 2 else min(score, 0.4)

    def parse(self, content: bytes | str, *, filename: str | None = None) -> list[dict[str, Any]]:
        if isinstance(content, bytes):
            content = content.decode("utf-8-sig")
        return list(csv.DictReader(io.StringIO(content)))

    def normalize(self, raw: list[dict[str, Any]], *, mapping: dict[str, Any] | None = None) -> CanonicalDataset:
        return build_match_summary(raw, source_system=self.format_id, overrides=mapping)


register_adapter(CsvScorecardAdapter())
