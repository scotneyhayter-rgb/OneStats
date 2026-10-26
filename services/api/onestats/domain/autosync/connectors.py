"""AutoSync connectors & catalog (Phase 9, Stage 9.2).

A connector is a :class:`~onestats.domain.importing.sync.SyncSource` plus metadata. Real online
connectors are registered **only when their access method and data structure are verified**; until
then a provider is a catalog entry with ``status='interface_only'`` that cannot fetch — documented,
never claimed to work. A deterministic :class:`FixtureConnector` lets the whole discovery→import→
approval path be tested without any external website.

No endpoints are invented and no authentication, paywall or anti-bot control is ever bypassed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from onestats.domain.importing.sync import SyncBatch, SyncCursor
from onestats.domain.importing.tabular import build_match_summary

# connector status: a live, verified connector; a deterministic test fixture; or an interface that is
# documented but NOT implemented because access/structure is not yet verified.
STATUS_LIVE = "live"
STATUS_FIXTURE = "fixture"
STATUS_INTERFACE_ONLY = "interface_only"
# implemented against a documented API, but requires credentials (an API key) before it can fetch; it is
# NOT interface-only (the code exists) and NOT yet live-verified against real responses.
STATUS_NEEDS_CREDENTIALS = "needs_credentials"


@dataclass(slots=True)
class ConnectorInfo:
    connector_id: str
    provider: str
    access_method: str                 # api | feed | file | fixture | (unspecified for interface_only)
    status: str = STATUS_INTERFACE_ONLY
    countries: list[str] = field(default_factory=list)
    formats: list[str] = field(default_factory=list)
    coverage: str | None = None
    auth_required: bool = False
    version: str = "0.1"
    notes: str | None = None


class FixtureConnector:
    """A deterministic source backed by in-memory match-summary rows — for tests and demos, never a
    real provider. Implements the SyncSource contract."""

    def __init__(self, source_system: str, rows: list[dict[str, Any]], *,
                 updated_rows: list[dict[str, Any]] | None = None, countries=None, formats=None,
                 provider: str = "Fixture source"):
        self.source_system = source_system
        self.format_id = "generic_json"
        self._rows = rows
        self._updated = updated_rows or []
        self.info = ConnectorInfo(connector_id=source_system, provider=provider,
                                  access_method="fixture", status=STATUS_FIXTURE,
                                  countries=countries or [], formats=formats or [],
                                  coverage="deterministic sample data (not a live source)")

    def _batch(self, rows: list[dict[str, Any]]) -> SyncBatch:
        ds = build_match_summary(rows, source_system=self.source_system)
        last = ds.matches[-1].source_ref if ds.matches else None
        return SyncBatch(dataset=ds, cursor=SyncCursor(self.source_system, last_ref=last,
                                                       last_seen_at=datetime.now(UTC)))

    def fetch_new(self, since: SyncCursor | None) -> SyncBatch:
        # first poll yields all rows; a subsequent poll (cursor set) yields nothing new
        return self._batch([] if since and since.last_ref else self._rows)

    def fetch_updated(self, since: SyncCursor | None) -> SyncBatch:
        return self._batch(self._updated)


class InterfaceOnlyConnector:
    """A documented provider whose connector is NOT implemented (access/structure unverified). It
    carries metadata but refuses to fetch, so nothing is ever fabricated for it."""

    def __init__(self, info: ConnectorInfo):
        self.source_system = info.connector_id
        self.format_id = ""
        self.info = info

    def fetch_new(self, since: SyncCursor | None) -> SyncBatch:
        raise NotImplementedError(f"{self.info.connector_id}: connector not implemented — {self._why()}")

    def fetch_updated(self, since: SyncCursor | None) -> SyncBatch:
        raise NotImplementedError(f"{self.info.connector_id}: connector not implemented — {self._why()}")

    def _why(self) -> str:
        return self.info.notes or "awaiting verified access / sample data"


class ConnectorCatalog:
    def __init__(self) -> None:
        self._by_id: dict[str, Any] = {}

    def register(self, connector: Any) -> Any:
        self._by_id[connector.info.connector_id] = connector
        return connector

    def get(self, connector_id: str):
        try:
            return self._by_id[connector_id]
        except KeyError as exc:
            raise ValueError(f"unknown connector: {connector_id}") from exc

    def all(self) -> list[Any]:
        return list(self._by_id.values())

    def describe(self) -> list[dict[str, Any]]:
        out = []
        for c in self._by_id.values():
            i = c.info
            out.append({"connector_id": i.connector_id, "provider": i.provider, "status": i.status,
                        "access_method": i.access_method, "countries": i.countries, "formats": i.formats,
                        "coverage": i.coverage, "auth_required": i.auth_required, "version": i.version,
                        "notes": i.notes})
        return out


catalog = ConnectorCatalog()

# Documented real providers — interface-ready, NOT implemented (no verified access/sample yet).
# Adding a real connector is a verify-then-implement step; these never fetch or fabricate data.
for _info in (
    ConnectorInfo("play_cricket", "Play-Cricket (ECB)", access_method="api", status=STATUS_INTERFACE_ONLY,
                  countries=["GB"], formats=["One-Day", "T20", "Multi-Day"], auth_required=True,
                  notes="ECB Play-Cricket API key + site registration required; structure unverified."),
    ConnectorInfo("cricket_archive", "CricketArchive", access_method="feed", status=STATUS_INTERFACE_ONLY,
                  countries=["*"], formats=["Test", "First-Class", "List A", "ODI", "T20I"], auth_required=True,
                  notes="Licensed historical dataset; commercial agreement required."),
    # Phase 10, Stage 10.3 — historical newspaper / archive sources. Interface-only until verified,
    # legitimate access terms exist; no access is assumed from a website alone and no paywall/anti-bot
    # control is ever bypassed. Development runs on uploaded documents and fixtures instead.
    ConnectorInfo("trove", "Trove (National Library of Australia)", access_method="api",
                  status=STATUS_INTERFACE_ONLY, countries=["AU"], formats=["Newspaper"], auth_required=True,
                  notes="Trove API key + adherence to NLA terms of use required; structure unverified."),
    ConnectorInfo("newspaper_archive", "Historical newspaper archive (generic)", access_method="api",
                  status=STATUS_INTERFACE_ONLY, countries=["*"], formats=["Newspaper"], auth_required=True,
                  notes="A placeholder for a licensed/permitted newspaper collection; access terms required."),
    ConnectorInfo("library_collection", "National/State library collection (generic)", access_method="api",
                  status=STATUS_INTERFACE_ONLY, countries=["*"], formats=["Newspaper", "Publication"],
                  auth_required=True, notes="Institutional access/agreement required; structure unverified."),
):
    catalog.register(InterfaceOnlyConnector(_info))

# A built-in, clearly-labelled SAMPLE source (deterministic fixture data — NOT a live provider), so
# AutoSync can be exercised end to end in any workspace without external access. Two seasons of club
# matches, with one updated result for the updated-scorecard flow.
SAMPLE_ROWS = [
    {"Date": "2023-11-04", "HomeTeam": "Sandbox Swifts", "AwayTeam": "Sandbox Saints",
     "Competition": "Sandbox Saturday League", "Grade": "A Grade", "Venue": "Sample Oval",
     "Result": "Home win", "Format": "One-Day", "Round": "1"},
    {"Date": "2023-11-11", "HomeTeam": "Sandbox Saints", "AwayTeam": "Sandbox Strikers",
     "Competition": "Sandbox Saturday League", "Grade": "A Grade", "Venue": "Sample Park",
     "Result": "Away win", "Format": "One-Day", "Round": "2"},
    {"Date": "2024-01-20", "HomeTeam": "Sandbox Swifts", "AwayTeam": "Sandbox Strikers",
     "Competition": "Sandbox Saturday League", "Grade": "A Grade", "Venue": "Sample Oval",
     "Result": "Tie", "Format": "T20", "Round": "9"},
]
SAMPLE_UPDATED = [
    # the source now reports a corrected result for the first match (for the updated-scorecard test)
    {**SAMPLE_ROWS[0], "Result": "Tie"},
]
catalog.register(FixtureConnector("onestats_sample", SAMPLE_ROWS, updated_rows=SAMPLE_UPDATED,
                                  countries=["AU"], formats=["One-Day", "T20"],
                                  provider="OneStats sample (fixture)"))

# A second clearly-labelled sample source (a "newspaper" fixture) reporting the SAME first fixture
# with a different result — to demonstrate possible-duplicate detection and multiple-sources-per-match
# (R1) with a conflict. Deterministic fixture data, NOT a live source.
SAMPLE_NEWS_ROWS = [
    {"Date": "2023-11-04", "HomeTeam": "Sandbox Swifts", "AwayTeam": "Sandbox Saints",
     "Competition": "Sandbox Saturday League", "Grade": "A Grade", "Venue": "Sample Oval",
     "Result": "Tie", "Format": "One-Day", "Round": "1"},
]
catalog.register(FixtureConnector("onestats_sample_news", SAMPLE_NEWS_ROWS,
                                  countries=["AU"], formats=["One-Day"],
                                  provider="OneStats sample newspaper (fixture)"))

# The real PlayHQ connector (RMCC's platform). Implemented against PlayHQ's documented public API; it
# fetches only when an API key is configured, otherwise it reports clearly that credentials are needed.
# Imported here (after the catalog + base classes are defined) to avoid a circular import.
from onestats.domain.autosync.playhq import PlayHQConnector

catalog.register(PlayHQConnector())
