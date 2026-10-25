"""Canonical Cricket Data Model (CCDM) — Phase 8, Stage 8.1.

A single neutral, typed intermediate representation that every source adapter produces. The shared
core pipeline stages / matches / validates / commits the CCDM, so adding a new source means writing a
parser + a normaliser to this model — never touching the pipeline.

Invariants encoded here (inherited from Phases 5–7):

* **Unknown is never zero.** Numeric fields are ``int | None``; ``None`` means *not established*, and
  ``0`` is a real recorded zero. Adapters must map a blank/absent source value to ``None``.
* **Provenance travels with every entity.** ``source_ref`` (the source's own id, verbatim) and, where
  the source has one, ``source_display_name`` (the original name/abbreviation) are preserved.
* **Nothing is invented.** A field the source does not provide stays ``None``; adapters never guess a
  captain, keeper, toss, score or dismissal.

These dataclasses are deliberately close to the existing ``normalised`` staging payloads so the
CricketStatz refactor (Stage 8.2) and the generic stager converge without data loss.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

# Neutral vocabularies (mirror the domain modules; adapters map their source codes to these).
TossWinner = str  # "home" | "away" | None  (never inferred from batting order or result)
DatePrecision = str  # "exact" | "month" | "year" | "unknown"


def clean_ref(value: Any) -> str | None:
    """A source reference as a non-empty string, or ``None``. Blank/``None`` → ``None``. Does not
    treat ``0`` specially — an adapter whose ``0`` means *none* converts it before calling this."""
    if value is None:
        return None
    s = str(value).strip()
    return s or None


@dataclass(slots=True)
class CanonicalClub:
    source_ref: str
    name: str | None = None
    source_display_name: str | None = None


@dataclass(slots=True)
class CanonicalTeam:
    source_ref: str
    name: str | None = None
    club_ref: str | None = None
    source_display_name: str | None = None
    aliases: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CanonicalVenue:
    source_ref: str
    name: str | None = None
    source_display_name: str | None = None


@dataclass(slots=True)
class CanonicalGrade:
    source_ref: str
    name: str | None = None


@dataclass(slots=True)
class CanonicalCompetition:
    source_ref: str
    name: str | None = None
    season_model: str | None = None


@dataclass(slots=True)
class CanonicalSeason:
    source_ref: str
    label: str | None = None
    start_date: date | None = None
    end_date: date | None = None


@dataclass(slots=True)
class CanonicalPerson:
    source_ref: str
    display_name: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    dob: date | None = None
    dob_precision: DatePrecision = "unknown"
    club_ref: str | None = None  # the source's "home" club (e.g. MyClub), for affiliation linking
    source_display_name: str | None = None


@dataclass(slots=True)
class CanonicalBattingEntry:
    batting_position: int | None = None
    person_ref: str | None = None
    dismissal_type: str | None = None          # mapped neutral type, or None if unresolved
    dismissal_source_code: str | None = None    # raw source code, ALWAYS preserved
    bowler_ref: str | None = None
    fielder_ref: str | None = None
    runs: int | None = None
    balls_faced: int | None = None
    fours: int | None = None
    sixes: int | None = None
    minutes: int | None = None
    # fall-of-wicket hints carried on the batting row by some sources
    fow_score: int | None = None
    fow_position: int | None = None
    fow_bat_ref: str | None = None
    fow_overs: float | None = None


@dataclass(slots=True)
class CanonicalBowlingEntry:
    person_ref: str | None = None
    overs: float | None = None
    legal_balls: int | None = None
    maidens: int | None = None
    runs_conceded: int | None = None
    wickets: int | None = None
    wides: int | None = None
    noballs: int | None = None


@dataclass(slots=True)
class CanonicalFow:
    wicket_number: int | None = None
    team_score: int | None = None
    dismissed_ref: str | None = None
    overs: float | None = None


@dataclass(slots=True)
class CanonicalInnings:
    source_ref: str
    number: int | None = None
    batting_team_ref: str | None = None
    bowling_team_ref: str | None = None
    byes: int | None = None
    legbyes: int | None = None
    wides: int | None = None
    noballs: int | None = None
    penalty: int | None = None
    official_total: int | None = None
    official_wickets: int | None = None
    batting: list[CanonicalBattingEntry] = field(default_factory=list)
    bowling: list[CanonicalBowlingEntry] = field(default_factory=list)
    fall_of_wickets: list[CanonicalFow] = field(default_factory=list)


@dataclass(slots=True)
class CanonicalMatch:
    source_ref: str
    match_date: date | None = None
    date_precision: DatePrecision = "unknown"
    home_team_ref: str | None = None
    away_team_ref: str | None = None
    competition_ref: str | None = None
    season_ref: str | None = None
    grade_ref: str | None = None
    venue_ref: str | None = None
    round: str | None = None            # a label only, never used to classify
    match_format: str | None = None
    result_code: str | None = None       # raw source result code, preserved
    result_type: str | None = None       # mapped neutral result, or None if unresolved
    result_status: str = "unresolved"    # "known" | "unresolved"
    # match-specific roles (0/absent → None; a person set as both captain and keeper keeps both)
    home_captain_ref: str | None = None
    home_keeper_ref: str | None = None
    home_keeper2_ref: str | None = None
    away_captain_ref: str | None = None
    away_keeper_ref: str | None = None
    away_keeper2_ref: str | None = None
    toss_won_by: TossWinner | None = None   # "home" | "away" | None — never inferred
    innings: list[CanonicalInnings] = field(default_factory=list)


@dataclass(slots=True)
class SourceProvenance:
    """Where a dataset came from — recorded on the import batch and carried for R1 multi-source."""
    source_system: str
    filename: str | None = None
    sha256: str | None = None
    edition: str | None = None          # e.g. a newspaper edition label (R1)
    imported_at: datetime | None = None


@dataclass(slots=True)
class CanonicalDataset:
    """One source's full contribution, normalised. The pipeline stages/matches/commits this."""
    provenance: SourceProvenance
    clubs: list[CanonicalClub] = field(default_factory=list)
    teams: list[CanonicalTeam] = field(default_factory=list)
    venues: list[CanonicalVenue] = field(default_factory=list)
    grades: list[CanonicalGrade] = field(default_factory=list)
    competitions: list[CanonicalCompetition] = field(default_factory=list)
    seasons: list[CanonicalSeason] = field(default_factory=list)
    people: list[CanonicalPerson] = field(default_factory=list)
    matches: list[CanonicalMatch] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        """Per-entity totals (for batch ``counts`` and preview)."""
        return {
            "clubs": len(self.clubs), "teams": len(self.teams), "venues": len(self.venues),
            "grades": len(self.grades), "competitions": len(self.competitions),
            "seasons": len(self.seasons), "people": len(self.people), "matches": len(self.matches),
            "innings": sum(len(m.innings) for m in self.matches),
            "batting": sum(len(i.batting) for m in self.matches for i in m.innings),
            "bowling": sum(len(i.bowling) for m in self.matches for i in m.innings),
            "fall_of_wickets": sum(len(i.fall_of_wickets) for m in self.matches for i in m.innings),
        }

    def validate_provenance(self) -> list[str]:
        """Structural checks that nothing lost its source identity. Returns human-readable problems
        (empty when clean). Does NOT judge cricketing correctness — that is the validation stage."""
        problems: list[str] = []
        if not self.provenance.source_system:
            problems.append("dataset has no source_system")
        for label, rows in (("club", self.clubs), ("team", self.teams), ("venue", self.venues),
                            ("grade", self.grades), ("competition", self.competitions),
                            ("season", self.seasons), ("person", self.people), ("match", self.matches)):
            for i, r in enumerate(rows):
                if not getattr(r, "source_ref", None):
                    problems.append(f"{label}[{i}] has no source_ref (provenance lost)")
        return problems
