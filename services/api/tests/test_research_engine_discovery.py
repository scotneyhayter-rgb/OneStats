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

    def fake_search(settings, *, query, year_from=None, year_to=None, n=5, api_key=None, base_url=None):
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

    def fake_search(settings, *, query, year_from=None, year_to=None, n=5, api_key=None, base_url=None):
        seen["api_key"] = api_key
        return {"results": [{"url": "https://trove.nla.gov.au/a/1"}]}

    monkeypatch.setattr("onestats.domain.research.trove.search_newspapers", fake_search)
    out = engine.discover_trove(["x"], None, settings=ENV_KEY)   # no explicit key → env key used
    assert out and seen["api_key"] == "ENV-TROVE-KEY"


def test_discover_trove_without_any_key_yields_nothing():
    # No workspace key and no env key → Trove contributes nothing (and never fabricates a candidate).
    assert engine.discover_trove(["anything"], {"year": 1900}, settings=NO_KEY) == []
