"""Source adapters for the universal import framework (Phase 8).

Importing this package registers the built-in adapters in the process-wide registry. New adapters add
a module here and a ``register_adapter(...)`` call; the pipeline never changes.
"""
from __future__ import annotations

from onestats.domain.importing.adapters import (
    cricket_statz,
    csv_scorecard,
    excel_scorecard,
    json_generic,
    xml_generic,
)

__all__ = ["cricket_statz", "csv_scorecard", "excel_scorecard", "json_generic", "xml_generic"]
