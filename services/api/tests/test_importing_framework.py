"""Phase 8, Stage 8.1 — the adapter core: Canonical Cricket Data Model + adapter contract/registry.

Pure logic (no database): the model preserves provenance and keeps unknown distinct from zero, and
the registry registers, looks up and detects adapters by confidence. Adding a format is a new adapter,
never a pipeline change.
"""
from __future__ import annotations

import pytest

from onestats.domain.importing import model as m
from onestats.domain.importing.adapter import AdapterRegistry, SourceAdapter
from onestats.domain.importing.model import (
    CanonicalBattingEntry,
    CanonicalDataset,
    CanonicalInnings,
    CanonicalMatch,
    CanonicalTeam,
    SourceProvenance,
)


def _dataset() -> CanonicalDataset:
    ds = CanonicalDataset(provenance=SourceProvenance(source_system="demo", filename="f.json"))
    ds.teams = [CanonicalTeam(source_ref="100", name="Alpha"), CanonicalTeam(source_ref="200", name="Beta")]
    inn = CanonicalInnings(source_ref="700", number=1, batting_team_ref="100", bowling_team_ref="200",
                           batting=[CanonicalBattingEntry(batting_position=1, person_ref="10", runs=38),
                                    CanonicalBattingEntry(batting_position=2, person_ref="11")])
    ds.matches = [CanonicalMatch(source_ref="500", home_team_ref="100", away_team_ref="200", innings=[inn])]
    return ds


# ---- model ----------------------------------------------------------------------------------------

def test_clean_ref_blank_and_whitespace_become_none():
    assert m.clean_ref(None) is None
    assert m.clean_ref("") is None
    assert m.clean_ref("   ") is None
    assert m.clean_ref("361481") == "361481"
    assert m.clean_ref(361481) == "361481"
    # 0 is NOT special here — a source whose 0 means "none" converts before calling clean_ref
    assert m.clean_ref(0) == "0"


def test_unknown_is_not_zero():
    """A batter who faced an unknown number of balls is None, distinct from 0 balls faced."""
    b = CanonicalBattingEntry(batting_position=3, person_ref="12", runs=0, balls_faced=None)
    assert b.runs == 0            # a real recorded zero
    assert b.balls_faced is None  # unknown, never coerced to 0


def test_counts_rolls_up_nested_entities():
    c = _dataset().counts()
    assert c["teams"] == 2 and c["matches"] == 1 and c["innings"] == 1 and c["batting"] == 2
    assert c["bowling"] == 0 and c["fall_of_wickets"] == 0


def test_validate_provenance_clean_and_dirty():
    assert _dataset().validate_provenance() == []
    bad = _dataset()
    bad.teams[0].source_ref = ""          # provenance lost
    bad.provenance.source_system = ""
    problems = bad.validate_provenance()
    assert any("source_system" in p for p in problems)
    assert any("team[0]" in p for p in problems)


# ---- adapter registry -----------------------------------------------------------------------------

class _DummyAdapter(SourceAdapter):
    format_id = "dummy"
    display_name = "Dummy"
    capabilities = frozenset({"matches"})

    def __init__(self, marker: str = "DUMMY"):
        self.marker = marker

    def detect(self, sample, filename=None):
        text = sample.decode() if isinstance(sample, bytes) else sample
        return 0.9 if self.marker in text else 0.0

    def parse(self, content, *, filename=None):
        return {"raw": content}

    def normalize(self, raw, *, mapping=None):
        return CanonicalDataset(provenance=SourceProvenance(source_system="dummy"))


class _OtherAdapter(_DummyAdapter):
    format_id = "other"
    display_name = "Other"

    def detect(self, sample, filename=None):
        text = sample.decode() if isinstance(sample, bytes) else sample
        return 0.6 if "OTHER" in text else 0.0


def test_register_get_and_duplicate_guard():
    reg = AdapterRegistry()
    a = reg.register(_DummyAdapter())
    assert reg.get("dummy") is a
    assert [x.format_id for x in reg.all()] == ["dummy"]
    with pytest.raises(ValueError, match="already registered"):
        reg.register(_DummyAdapter())
    with pytest.raises(ValueError, match="unknown import format"):
        reg.get("nope")


def test_detect_picks_highest_confidence_above_threshold():
    reg = AdapterRegistry()
    reg.register(_DummyAdapter())
    reg.register(_OtherAdapter())
    # a file both claim: dummy (0.9) beats other (0.6)
    best = reg.best("has DUMMY and OTHER markers")
    assert best is not None and best.format_id == "dummy"
    # only the other adapter is confident
    assert reg.best("OTHER only").format_id == "other"
    # nothing confident -> no match (wizard will ask the user)
    assert reg.best("nothing recognisable") is None


def test_detect_is_resilient_to_a_misbehaving_adapter():
    class _Boom(_DummyAdapter):
        format_id = "boom"
        def detect(self, sample, filename=None):
            raise RuntimeError("kaboom")
    reg = AdapterRegistry()
    reg.register(_Boom())
    reg.register(_DummyAdapter())
    # the exploding adapter is scored 0, the good one still wins
    assert reg.best("DUMMY here").format_id == "dummy"


def test_adapter_requires_format_id():
    class _NoId(_DummyAdapter):
        format_id = ""
    with pytest.raises(ValueError, match="non-empty format_id"):
        AdapterRegistry().register(_NoId())
