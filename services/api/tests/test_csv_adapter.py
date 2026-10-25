"""Phase 8, Stage 8.3 — the mapping engine + generic CSV adapter.

Pure logic (no database). The mapping engine coerces cells (blank → None, unknown never zero) and
remaps columns; the CSV adapter turns a match-summary CSV into the Canonical model with deterministic
(idempotent) refs, classifying a result only when the text clearly says so.
"""
from __future__ import annotations

from datetime import date

from onestats.domain.importing import detect_adapter, registry
from onestats.domain.importing.adapters.csv_scorecard import CsvScorecardAdapter
from onestats.domain.importing.mapping import FieldRule, MappingTemplate, coerce, slugify

CSV = (
    "Date,HomeTeam,AwayTeam,Competition,Grade,Venue,Result,Format,Round\n"
    "2024-01-06,Alpha CC,Beta CC,Saturday League,A Grade,Alpha Oval,Home win,One-day,1\n"
    "2024-01-13,Beta CC,Alpha CC,Saturday League,A Grade,Beta Park,,One-day,2\n"   # result blank → unresolved
)


# ---- mapping engine -------------------------------------------------------------------------------

def test_coerce_blank_is_none_and_unknown_not_zero():
    assert coerce("", "int") is None            # unknown, not 0
    assert coerce("  ", "str") is None
    assert coerce("0", "int") == 0              # a real zero
    assert coerce("12.5", "float") == 12.5
    assert coerce("not a number", "int") is None
    assert coerce("yes", "bool") is True and coerce("n", "bool") is False
    assert coerce("2024-01-06", "date") == date(2024, 1, 6)
    assert coerce("06/01/2024", "date") == date(2024, 1, 6)   # d/m/y


def test_slugify_is_stable_and_blank_is_none():
    assert slugify("Wick/L Bolac") == "wick-l-bolac"
    assert slugify("  Alpha  CC ") == "alpha-cc"
    assert slugify("") is None
    assert slugify("Alpha CC") == slugify("alpha cc")   # deterministic, case-insensitive


def test_template_apply_with_override():
    t = MappingTemplate("t", "match", [FieldRule("home_team", "HomeTeam", "str")])
    assert t.apply({"HomeTeam": "Alpha"})["home_team"] == "Alpha"
    # override points the canonical field at a different column
    assert t.apply({"Host": "Beta"}, overrides={"home_team": "Host"})["home_team"] == "Beta"


# ---- CSV adapter ----------------------------------------------------------------------------------

def test_detect_and_registration():
    a = CsvScorecardAdapter()
    assert a.detect(CSV, "fixtures.csv") > 0.6
    assert a.detect("just,some,random,columns\n1,2,3,4") < 0.6   # not a match summary
    assert registry.get("csv_scorecard").format_id == "csv_scorecard"
    # a CSV routes to the CSV adapter, a CricketStatz JSON does not
    assert detect_adapter(CSV, "fixtures.csv").format_id == "csv_scorecard"


def test_normalize_builds_dedup_teams_and_matches():
    ds = CsvScorecardAdapter().normalize(CsvScorecardAdapter().parse(CSV))
    assert ds.provenance.source_system == "csv_scorecard"
    assert ds.validate_provenance() == []
    # two teams only, despite appearing on both sides across two matches
    assert {t.source_ref for t in ds.teams} == {"alpha-cc", "beta-cc"}
    assert len(ds.matches) == 2
    m1 = ds.matches[0]
    assert m1.home_team_ref == "alpha-cc" and m1.away_team_ref == "beta-cc"
    assert m1.match_date == date(2024, 1, 6) and m1.match_format == "One-day"
    assert m1.result_type == "home_win" and m1.result_status == "known"
    # blank result → unresolved, raw preserved as None (nothing invented)
    assert ds.matches[1].result_type is None and ds.matches[1].result_status == "unresolved"


def test_match_refs_are_deterministic_for_idempotent_reimport():
    a = CsvScorecardAdapter()
    refs1 = [m.source_ref for m in a.normalize(a.parse(CSV)).matches]
    refs2 = [m.source_ref for m in a.normalize(a.parse(CSV)).matches]
    assert refs1 == refs2 and len(set(refs1)) == 2   # stable + unique per match
