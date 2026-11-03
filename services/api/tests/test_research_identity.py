"""Player identity SUGGESTION (never auto-link/merge). Pure/offline over an in-memory person index."""
from __future__ import annotations

from onestats.domain.research import identity, webextract

INDEX = [
    {"person_id": "p1", "display_name": "John Smith", "tokens": identity._tokens("John Smith")},
    {"person_id": "p2", "display_name": "Alan Walker", "tokens": identity._tokens("Alan Walker")},
]


def test_suggests_on_shared_surname():
    out = identity.suggest(["J Smith", "A Walker"], INDEX)
    assert out["J Smith"][0]["person_id"] == "p1"
    assert out["A Walker"][0]["person_id"] == "p2"


def test_initial_only_name_does_not_match():
    # A bare initial must never raise a candidate (a name is never proof of identity).
    assert identity.suggest(["J"], INDEX) == {}


def test_unknown_surname_yields_no_suggestion():
    assert identity.suggest(["T Bonner"], INDEX) == {}


def test_player_name_parsing_from_scorecard_lines():
    lines = [
        "J Smith c Jones b Brown 34",
        "A Walker not out 21",
        "T Bonner lbw b Green 7",
        "Extras (b 4, lb 2) 6",
    ]
    names = webextract.player_names_from_lines(lines)
    assert "J Smith" in names and "A Walker" in names and "T Bonner" in names
