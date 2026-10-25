"""Generic JSON adapter — Phase 8, Stage 8.4.

Imports a structured JSON **array of match objects** (one object per match, keys like HomeTeam /
AwayTeam / Date). Distinct from the CricketStatz adapter, which takes a JSON *object* with nested
``matches``/``players`` collections — so a CricketStatz export is not misrouted here. Rows are handed
to the shared tabular builder; blank fields are unknown, nothing is invented.
"""
from __future__ import annotations

import json
from typing import Any

from onestats.domain.importing.adapter import SourceAdapter, register_adapter
from onestats.domain.importing.model import CanonicalDataset
from onestats.domain.importing.tabular import build_match_summary


class JsonGenericAdapter(SourceAdapter):
    format_id = "generic_json"
    display_name = "JSON match list"
    capabilities = frozenset({"matches"})

    def detect(self, sample: bytes | str, filename: str | None = None) -> float:
        text = sample.decode("utf-8-sig", errors="ignore") if isinstance(sample, bytes) else sample
        head = text.lstrip()[:2000].lower()
        if not head.startswith("["):      # an array of match objects (a CS export starts with '{')
            return 0.0
        score = 0.4
        for marker in ("hometeam", "awayteam", "home team", "away team", "\"date\"", "result"):
            if marker in head:
                score += 0.12
        return min(score, 0.9)

    def parse(self, content: bytes | str, *, filename: str | None = None) -> list[dict[str, Any]]:
        if isinstance(content, bytes):
            content = content.decode("utf-8-sig")
        data = json.loads(content)
        if not isinstance(data, list):
            # not an array of matches — the CricketStatz adapter handles the object shape
            raise ValueError("generic_json: expected a top-level JSON array of match objects")  # noqa: TRY004
        return [r for r in data if isinstance(r, dict)]

    def normalize(self, raw: list[dict[str, Any]], *, mapping: dict[str, Any] | None = None) -> CanonicalDataset:
        return build_match_summary(raw, source_system=self.format_id, overrides=mapping)


register_adapter(JsonGenericAdapter())
