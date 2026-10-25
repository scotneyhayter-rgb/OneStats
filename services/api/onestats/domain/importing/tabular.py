"""Shared tabular → Canonical builder (Phase 8, Stage 8.4).

CSV, Excel, JSON and XML match-summary sources all reduce to a list of row dicts; this turns those
rows into a :class:`CanonicalDataset` via the mapping engine. One builder, four adapters: each adapter
only detects its format and parses to rows, then calls :func:`build_match_summary`.

Nothing is invented: a blank cell is unknown (``None``), a result is classified only when the text
clearly says so (raw preserved otherwise), and refs are deterministic (slugified) so re-importing the
same data is idempotent. A match-summary source has no clubs, so each team's name is treated as its
own club (club cricket shares the name) to make the team promotable — never a fabricated identity.
"""
from __future__ import annotations

from typing import Any

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

# columns a match-summary source is expected to carry (for adapter detection, case-insensitive)
SUMMARY_COLUMNS = {"hometeam", "awayteam", "home team", "away team", "date", "result", "competition", "venue", "grade"}


def classify_result(raw: str | None) -> str | None:
    """Canonical result type only when the text clearly says so; never guessed from team names."""
    if not raw:
        return None
    return _RESULT_TOKENS.get(str(raw).strip().lower())


def build_match_summary(
    rows: list[dict[str, Any]], *, source_system: str, filename: str | None = None,
    overrides: dict[str, str] | None = None, template: MappingTemplate = MATCH_SUMMARY,
) -> CanonicalDataset:
    ds = CanonicalDataset(provenance=SourceProvenance(source_system=source_system, filename=filename))
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
        ref = slugify(name)
        if ref and ref not in teams:
            clubs.setdefault(ref, CanonicalClub(source_ref=ref, name=name))
            teams[ref] = CanonicalTeam(source_ref=ref, name=name, club_ref=ref, source_display_name=name)
        return ref

    for row in rows:
        v = template.apply(row, overrides=overrides)
        home_ref = _team_ref(v["home_team"])
        away_ref = _team_ref(v["away_team"])
        comp_ref = _ref(comps, v["competition"], lambda r, n: CanonicalCompetition(source_ref=r, name=n))
        grade_ref = _ref(grades, v["grade"], lambda r, n: CanonicalGrade(source_ref=r, name=n))
        venue_ref = _ref(venues, v["venue"], lambda r, n: CanonicalVenue(source_ref=r, name=n))
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
            result_type=classify_result(result_raw),
            result_status="known" if classify_result(result_raw) else "unresolved",
        ))
    ds.clubs = list(clubs.values())
    ds.teams = list(teams.values())
    ds.competitions = list(comps.values())
    ds.grades = list(grades.values())
    ds.venues = list(venues.values())
    return ds
