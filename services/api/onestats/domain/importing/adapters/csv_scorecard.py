"""Generic CSV adapter — Phase 8, Stage 8.3.

Imports a **match-summary CSV**: one row per match (teams, date, competition, grade, venue, result,
format, round). It uses the reusable mapping engine, so column names can be remapped in the wizard
without code. CSV rows carry no stable source ids, so deterministic refs are derived from the natural
keys (slugified names; a match ref of ``date|home|away``) — re-importing the same file yields the same
refs, keeping the import idempotent.

Richer per-ball/per-innings CSV templates can be added later; this establishes the mapping-driven
pattern. Nothing is invented: a blank cell is unknown (``None``), and a result is classified only when
the text clearly matches a canonical outcome — otherwise the raw text is preserved and left unresolved.
"""
from __future__ import annotations

import csv
import io
from typing import Any

from onestats.domain.importing.adapter import SourceAdapter, register_adapter
from onestats.domain.importing.mapping import FieldRule, MappingTemplate, slugify
from onestats.domain.importing.model import (
    CanonicalClub,
    CanonicalCompetition,
    CanonicalDataset,
    CanonicalGrade,
    CanonicalMatch,
    CanonicalTeam,
    CanonicalVenue,
    SourceProvenance,
)

MATCH_SUMMARY = MappingTemplate(
    name="match_summary",
    entity="match",
    rules=[
        FieldRule("match_date", "Date", "date"),
        FieldRule("home_team", "HomeTeam", "str"),
        FieldRule("away_team", "AwayTeam", "str"),
        FieldRule("competition", "Competition", "str"),
        FieldRule("grade", "Grade", "str"),
        FieldRule("venue", "Venue", "str"),
        FieldRule("result", "Result", "str"),
        FieldRule("match_format", "Format", "str"),
        FieldRule("round", "Round", "str"),
    ],
)

_RESULT_TOKENS = {
    "home_win": "home_win", "home win": "home_win", "home": "home_win",
    "away_win": "away_win", "away win": "away_win", "away": "away_win",
    "tie": "tie", "tied": "tie", "draw": "draw", "drawn": "draw",
    "no_result": "no_result", "no result": "no_result",
    "abandoned": "abandoned", "washout": "washout", "forfeit": "forfeit",
}


def _result(raw: str | None) -> str | None:
    """Canonical result type only when the text clearly says so; never guessed from team names."""
    if not raw:
        return None
    return _RESULT_TOKENS.get(raw.strip().lower())


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
        hits = len(cols & {"hometeam", "awayteam", "home team", "away team", "date", "result", "competition"})
        score = 0.0
        if filename and filename.lower().endswith(".csv"):
            score += 0.3
        score += min(hits * 0.2, 0.6)
        # needs at least two teams-ish/ date columns to be a match summary, not an arbitrary CSV
        return score if hits >= 2 else min(score, 0.4)

    def parse(self, content: bytes | str, *, filename: str | None = None) -> list[dict[str, Any]]:
        if isinstance(content, bytes):
            content = content.decode("utf-8-sig")
        return list(csv.DictReader(io.StringIO(content)))

    def normalize(self, raw: list[dict[str, Any]], *, mapping: dict[str, Any] | None = None) -> CanonicalDataset:
        overrides = mapping or {}
        ds = CanonicalDataset(provenance=SourceProvenance(source_system=self.format_id))
        teams: dict[str, CanonicalTeam] = {}
        clubs: dict[str, CanonicalClub] = {}
        comps: dict[str, CanonicalCompetition] = {}
        grades: dict[str, CanonicalGrade] = {}
        venues: dict[str, CanonicalVenue] = {}

        def _ref(bucket: dict, name: str | None, make) -> str | None:
            ref = slugify(name)
            if ref and ref not in bucket:
                bucket[ref] = make(ref, name)
            return ref

        def _team_ref(name: str | None) -> str | None:
            # a match-summary CSV has no clubs; treat each team's name as its own club so the team can
            # be promoted (club cricket: the team and its club share a name). No identity is invented.
            ref = slugify(name)
            if ref and ref not in teams:
                clubs.setdefault(ref, CanonicalClub(source_ref=ref, name=name))
                teams[ref] = CanonicalTeam(source_ref=ref, name=name, club_ref=ref, source_display_name=name)
            return ref

        for row in raw:
            v = MATCH_SUMMARY.apply(row, overrides=overrides)
            home_ref = _team_ref(v["home_team"])
            away_ref = _team_ref(v["away_team"])
            comp_ref = _ref(comps, v["competition"], lambda r, n: CanonicalCompetition(source_ref=r, name=n))
            grade_ref = _ref(grades, v["grade"], lambda r, n: CanonicalGrade(source_ref=r, name=n))
            venue_ref = _ref(venues, v["venue"], lambda r, n: CanonicalVenue(source_ref=r, name=n))
            # a deterministic match ref from its natural key (date + both teams) → idempotent re-import
            key = "|".join(str(x) for x in (v["match_date"], home_ref, away_ref))
            result_raw = v["result"]
            ds.matches.append(CanonicalMatch(
                source_ref=slugify(key) or key,
                match_date=v["match_date"],
                date_precision="exact" if v["match_date"] else "unknown",
                home_team_ref=home_ref, away_team_ref=away_ref,
                competition_ref=comp_ref, grade_ref=grade_ref, venue_ref=venue_ref,
                round=v["round"], match_format=v["match_format"],
                result_code=result_raw,
                result_type=_result(result_raw),
                result_status="known" if _result(result_raw) else "unresolved",
            ))
        ds.clubs = list(clubs.values())
        ds.teams = list(teams.values())
        ds.competitions = list(comps.values())
        ds.grades = list(grades.values())
        ds.venues = list(venues.values())
        return ds


register_adapter(CsvScorecardAdapter())
