"""International import source policy — the allow-list is enforceable and matches the agreed decision.

No database: these are pure checks on the policy module. They lock in that only the agreed open sources
are fetchable, that bot-blocked/proprietary sites are benchmarks (never fetched), that subdomains of an
allow-listed host are accepted while look-alikes are not, and that completeness needs >= 2 sources.
"""
from __future__ import annotations

from onestats.domain.intl import sources


def test_only_open_sources_are_fetchable():
    keys = {s.key for s in sources.fetchable_sources()}
    assert keys == {"cricsheet", "wikipedia", "wikidata"}
    # every fetchable source carries a host to match against
    assert all(s.host for s in sources.fetchable_sources())


def test_proprietary_sources_are_benchmarks_not_fetched():
    bench = {s.key for s in sources.benchmark_sources()}
    assert {"espncricinfo", "cricketstatz"} <= bench
    # ESPNcricinfo actively blocks bots: it must never be fetchable
    assert sources.is_fetchable("espncricinfo.com") is False
    assert sources.is_fetchable("www.espncricinfo.com") is False
    # benchmarks deliberately have no fetch host
    assert all(s.host is None for s in sources.benchmark_sources())


def test_is_fetchable_accepts_subdomains_but_not_lookalikes():
    assert sources.is_fetchable("cricsheet.org") is True
    assert sources.is_fetchable("https://www.cricsheet.org/downloads/") is True
    assert sources.is_fetchable("en.wikipedia.org") is True
    # a look-alike or unrelated host is refused
    assert sources.is_fetchable("cricsheet.org.evil.com") is False
    assert sources.is_fetchable("notcricsheet.org") is False
    assert sources.is_fetchable("") is False


def test_completeness_requires_two_sources():
    assert sources.MIN_SOURCES_FOR_COMPLETENESS == 2
