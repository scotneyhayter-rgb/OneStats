"""PlayHQ connector — traversal + defensive mapping, with a FAKE client (no live calls, no credentials).

Verifies the organisation → seasons → grades → grade-fixture traversal, the response → match-summary-row
mapping (defensive field names, unknown-aware), bye/placeholder skipping, cursor pagination, and that a
missing API key refuses to fetch rather than fabricating. The exact live field names still need validating
against real PlayHQ cricket (v2) responses once the key is entered.
"""
from __future__ import annotations

import pytest

from onestats.domain.autosync.playhq import (
    PlayHQClient,
    PlayHQConnector,
    _game_to_row,
    _result_text,
)


class FakeClient:
    """Stands in for PlayHQClient; returns canned responses by path (shape per PlayHQ's documented API)."""

    def __init__(self, pages: dict[str, list[dict]] | None = None):
        self.calls: list[str] = []
        self._pages = pages

    def get_all(self, path: str, params=None):
        self.calls.append(path)
        if path.endswith("/fixture"):
            return [
                {"id": "GM1", "date": "2024-11-02T10:00:00Z", "homeTeam": {"name": "Rhymney/Moyston"},
                 "awayTeam": {"name": "Pomonal"}, "venue": {"name": "Moyston Oval"}, "round": "Round 1",
                 "outcome": "COMPLETED", "winner": {"name": "Rhymney/Moyston"}, "format": "One Day"},
                {"id": "BYE", "homeTeam": None, "awayTeam": None},   # a bye → no teams → skipped
            ]
        if path.endswith("/grades"):
            return [{"id": "G1", "name": "A Grade"}]
        if path.endswith("/seasons"):
            return [{"id": "S1", "name": "2024/25"}]
        return []


def test_traversal_and_mapping():
    conn = PlayHQConnector(client_factory=lambda: FakeClient())
    batch = conn.fetch_new(None)
    ds = batch.dataset
    assert len(ds.matches) == 1                       # the bye was skipped
    m = ds.matches[0]
    assert str(m.match_date) == "2024-11-02" and m.round == "Round 1"
    assert m.result_code == "Home win" and m.result_type == "home_win"
    teams = {t.name for t in ds.teams}
    assert "Rhymney/Moyston" in teams and "Pomonal" in teams
    assert any(c.name == "2024/25" for c in ds.competitions)
    assert any(g.name == "A Grade" for g in ds.grades)


def test_game_to_row_defensive_fields():
    # alternative field names + a tie outcome, with unknown venue/format left as None
    row = _game_to_row({"startDate": "2023-03-15", "home": {"name": "A"}, "away": {"name": "B"},
                        "outcome": "TIE"}, season="2022/23", grade="B Grade")
    assert row == {"Date": "2023-03-15", "HomeTeam": "A", "AwayTeam": "B", "Competition": "2022/23",
                   "Grade": "B Grade", "Venue": None, "Result": "Tie", "Format": None, "Round": None}


def test_result_mapping_unknown_is_not_guessed():
    assert _result_text({"outcome": "abandoned"}) == "No result"
    assert _result_text({"outcome": "IN_PROGRESS"}) is None       # unknown → not guessed
    assert _result_text({"winner": {"name": "B"}, "homeTeam": {"name": "A"}, "awayTeam": {"name": "B"}}) == "Away win"


def test_missing_api_key_refuses_to_fetch(monkeypatch):
    from onestats.core import config
    monkeypatch.setattr(config.get_settings(), "playhq_api_key", None, raising=False)
    conn = PlayHQConnector()      # no injected client → reads settings → no key
    with pytest.raises(NotImplementedError, match="not configured"):
        conn.fetch_new(None)


def test_host_resolves_by_tenant():
    from onestats.domain.autosync.playhq import host_for_tenant
    assert host_for_tenant("ca") == "https://api.caprod.playhq.com"   # Cricket Australia region
    assert host_for_tenant("eu") == "https://api.euprod.playhq.com"
    assert host_for_tenant("au") == "https://api.playhq.com"          # AU/NZ default


def test_pagination_follows_cursor():
    seen = {"n": 0}

    class Paged(PlayHQClient):
        def __init__(self):
            super().__init__(api_key="k", tenant="ca", base_url="http://x")

        def get(self, path, params=None):
            seen["n"] += 1
            if params and params.get("cursor") == "c2":
                return {"data": [{"id": "b"}], "metadata": {"hasMore": False}}
            return {"data": [{"id": "a"}], "metadata": {"hasMore": True, "nextCursor": "c2"}}

    items = Paged().get_all("/v1/organisations/x/seasons")
    assert [i["id"] for i in items] == ["a", "b"] and seen["n"] == 2
