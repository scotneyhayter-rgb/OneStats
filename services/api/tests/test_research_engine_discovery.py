"""Internet Research Engine — Trove discovery key plumbing.

Confirms the engine's Trove discovery uses the API key it is handed (the workspace's resolved
credential), falls back to the global env key, and yields nothing when no key is available anywhere —
never fabricating candidates. No network: the Trove search is stubbed.
"""
from __future__ import annotations

from onestats.core.config import Settings
from onestats.domain.research import engine

NO_KEY = Settings(env="test", db_password=None, _env_file=None)
ENV_KEY = Settings(env="test", db_password=None, _env_file=None, trove_api_key="ENV-TROVE-KEY")


def test_discover_trove_uses_explicit_workspace_key(monkeypatch):
    seen: dict[str, object] = {}

    def fake_search(settings, *, query, year_from=None, year_to=None, n=5, sortby=None,
                    api_key=None, base_url=None):
        seen["api_key"] = api_key
        seen["base_url"] = base_url
        return {"results": [{"url": f"https://trove.nla.gov.au/a/{query}"}]}

    monkeypatch.setattr("onestats.domain.research.trove.search_newspapers", fake_search)
    out = engine.discover_trove(["moyston cricket"], {"year": 1900}, settings=NO_KEY,
                                api_key="WS-KEY", base_url="https://api.trove.nla.gov.au/v3")
    assert out and out[0]["source"] == "trove"
    assert seen["api_key"] == "WS-KEY"                       # the workspace key, not the (absent) env key
    assert seen["base_url"] == "https://api.trove.nla.gov.au/v3"


def test_discover_trove_falls_back_to_env_key(monkeypatch):
    seen: dict[str, object] = {}

    def fake_search(settings, *, query, year_from=None, year_to=None, n=5, sortby=None,
                    api_key=None, base_url=None):
        seen["api_key"] = api_key
        return {"results": [{"url": "https://trove.nla.gov.au/a/1"}]}

    monkeypatch.setattr("onestats.domain.research.trove.search_newspapers", fake_search)
    out = engine.discover_trove(["x"], None, settings=ENV_KEY)   # no explicit key → env key used
    assert out and seen["api_key"] == "ENV-TROVE-KEY"


def test_discover_trove_without_any_key_yields_nothing():
    # No workspace key and no env key → Trove contributes nothing (and never fabricates a candidate).
    assert engine.discover_trove(["anything"], {"year": 1900}, settings=NO_KEY) == []


def test_discover_trove_applies_year_range_relevance_and_cap(monkeypatch):
    seen: dict[str, object] = {}
    calls = {"n": 0}

    def fake_search(settings, *, query, year_from=None, year_to=None, n=5, sortby=None,
                    api_key=None, base_url=None):
        calls["n"] += 1
        seen.update(year_from=year_from, year_to=year_to, sortby=sortby, n=n)
        return {"results": [{"url": f"https://trove.nla.gov.au/a/{calls['n']}"}]}

    monkeypatch.setattr("onestats.domain.research.trove.search_newspapers", fake_search)
    out = engine.discover_trove(["moyston cricket", "rhymney cricket", "ararat cricket"],
                                {"year_from": 1924, "year_to": 1925}, settings=ENV_KEY, n=25, max_queries=2)
    assert seen["year_from"] == 1924 and seen["year_to"] == 1925   # date facet honoured
    assert seen["sortby"] == "relevance"                           # ranked, not oldest-first
    assert seen["n"] == 25                                         # depth-scaled cap passed through
    assert calls["n"] == 2 and len(out) == 2                       # max_queries respected


def test_extract_year_range():
    assert engine.extract_year_range("Rhymney Moyston 1924/25") == (1924, 1925)
    assert engine.extract_year_range("season 1924-1925") == (1924, 1925)
    assert engine.extract_year_range("matches 1950 to 1960") == (1950, 1960)
    assert engine.extract_year_range("the 1890s") == (1890, 1899)
    assert engine.extract_year_range("Moyston cricket 1924") == (1924, 1924)
    assert engine.extract_year_range("1899/00") == (1899, 1900)   # century rollover
    assert engine.extract_year_range("no year here") == (None, None)


def test_strip_years():
    assert engine.strip_years("Moyston cricket 1924") == "Moyston cricket"
    assert engine.strip_years("Rhymney v Moyston 1924/25 season") == "Rhymney v Moyston"
    assert engine.strip_years("Moyston cricket") == "Moyston cricket"   # unchanged when no year
