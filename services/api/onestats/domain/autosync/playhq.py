"""PlayHQ connector (Phase 8/9) — RMCC's live scoring platform.

Implements the documented PlayHQ public-API flow (organisation → seasons → grades → grade fixture →
public game summary) and produces the same match-summary rows the manual importer uses, so PlayHQ data
flows through the existing staging → validation → identity-match → preview → approval pipeline. Nothing is
auto-approved by the connector; imported matches stay draft for administrator review unless AutoSync is
explicitly in authorised mode.

Access (from PlayHQ's integration docs): public GET endpoints authenticated with headers ``x-api-key``
(the Client ID, a UUID) and ``x-phq-tenant`` (cricket = ``ca``); cursor pagination via
``metadata.hasMore`` / ``metadata.nextCursor``; seasons/teams/grades are v1, cricket fixture/ladder/game-
summary are v2. The exact v2 cricket **response field names are gated** (docs.playhq.com/tech), so the
response → row mapping below is deliberately **defensive and isolated** (it tries several likely field
names and treats anything missing as unknown, never invented) and must be validated against live
responses once the API key is entered. Without a configured API key the connector cannot fetch and says
so — it never fabricates data.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from onestats.core.config import get_settings
from onestats.domain.importing.sync import SyncBatch, SyncCursor
from onestats.domain.importing.tabular import build_match_summary

# Endpoint paths (v1 for seasons/grades/teams; v2 for cricket fixture/ladder/game summary). Paths are
# per PlayHQ's documented structure; confirm against the gated tech docs / live responses when enabling.
_SEASONS = "/v1/organisations/{org}/seasons"
_GRADES = "/v1/seasons/{season}/grades"
_FIXTURE = "/v2/grades/{grade}/fixture"


class PlayHQClient:
    """Thin httpx wrapper: authenticated GET + cursor pagination. Imported lazily so the module loads
    without httpx present (tests inject a fake client)."""

    def __init__(self, *, api_key: str, tenant: str, base_url: str) -> None:
        self._key = api_key
        self._tenant = tenant
        self._base = base_url.rstrip("/")

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        import httpx
        headers = {"x-api-key": self._key, "x-phq-tenant": self._tenant, "Accept": "application/json"}
        resp = httpx.get(self._base + path, headers=headers, params=params or {}, timeout=30.0)
        resp.raise_for_status()
        return resp.json()

    def get_all(self, path: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Follow ``metadata.hasMore`` / ``metadata.nextCursor`` and return the concatenated ``data``."""
        items: list[dict[str, Any]] = []
        cursor: str | None = None
        for _ in range(1000):  # hard cap guards against a malformed cursor loop
            p = dict(params or {})
            if cursor:
                p["cursor"] = cursor
            data = self.get(path, p)
            items.extend(data.get("data") or [])
            meta = data.get("metadata") or {}
            if not meta.get("hasMore"):
                break
            cursor = meta.get("nextCursor")
            if not cursor:
                break
        return items


def _pick(d: Any, *keys: str) -> Any:
    """First non-empty value among ``keys`` in a dict (defensive against unverified field names)."""
    if not isinstance(d, dict):
        return None
    for k in keys:
        v = d.get(k)
        if v not in (None, ""):
            return v
    return None


def _name(v: Any) -> str | None:
    """A display name from a value that may be a string or a nested {name/displayName} object."""
    if isinstance(v, str):
        return v
    return _pick(v, "name", "displayName", "fullName")


def _date(v: Any) -> str | None:
    s = v if isinstance(v, str) else _pick(v, "date", "startDate", "start")
    if isinstance(s, str) and len(s) >= 10:
        return s[:10]              # ISO date (YYYY-MM-DD); time/zone dropped for the match-summary row
    return None


def _result_text(game: dict[str, Any]) -> str | None:
    """Map a PlayHQ game outcome to the match-summary result vocabulary, defensively. Unknown stays None
    (never guessed) — the match then imports as draft with an unresolved result for review."""
    outcome = _pick(game, "outcome", "result", "status")
    winner = _name(_pick(game, "winner", "winningTeam"))
    home = _name(_pick(game, "homeTeam", "home"))
    away = _name(_pick(game, "awayTeam", "away"))
    text = str(outcome).lower() if outcome else ""
    if "tie" in text:
        return "Tie"
    if "draw" in text:
        return "Draw"
    if "abandon" in text or "washout" in text or "no result" in text or "cancel" in text:
        return "No result"
    if winner and home and winner == home:
        return "Home win"
    if winner and away and winner == away:
        return "Away win"
    return None


def _game_to_row(game: dict[str, Any], *, season: str | None, grade: str | None) -> dict[str, Any]:
    return {
        "Date": _date(_pick(game, "date", "startDate", "scheduledTime", "start")),
        "HomeTeam": _name(_pick(game, "homeTeam", "home", "team1")),
        "AwayTeam": _name(_pick(game, "awayTeam", "away", "team2")),
        "Competition": season,
        "Grade": grade,
        "Venue": _name(_pick(game, "venue", "ground", "location")),
        "Result": _result_text(game),
        "Format": _name(_pick(game, "format", "matchType")),
        "Round": str(_pick(game, "round", "roundName", "roundNumber") or "") or None,
    }


class PlayHQConnector:
    """Live PlayHQ source implementing the SyncSource contract. Requires a configured API key + org id."""

    source_system = "playhq"
    format_id = "playhq_json"

    def __init__(self, client_factory=None) -> None:
        self._client_factory = client_factory
        # imported lazily to avoid a circular import (connectors registers this connector)
        from onestats.domain.autosync.connectors import STATUS_NEEDS_CREDENTIALS, ConnectorInfo
        self.info = ConnectorInfo(
            connector_id="playhq", provider="PlayHQ", access_method="api",
            status=STATUS_NEEDS_CREDENTIALS, countries=["AU"],
            formats=["One-Day", "T20", "Multi-Day"], auth_required=True,
            notes="Implemented against PlayHQ's documented public API; set PLAYHQ_API_KEY to enable. "
                  "Response field mapping is provisional until validated against live cricket (v2) responses.")

    def _client(self) -> PlayHQClient:
        if self._client_factory is not None:
            return self._client_factory()
        s = get_settings()
        if not s.playhq_api_key:
            raise NotImplementedError("playhq: PLAYHQ_API_KEY not configured — enter the PlayHQ API key to enable live sync")
        if not s.playhq_org_id:
            raise NotImplementedError("playhq: organisation id not configured")
        return PlayHQClient(api_key=s.playhq_api_key, tenant=s.playhq_tenant, base_url=s.playhq_base_url)

    def _org_id(self) -> str:
        return get_settings().playhq_org_id or ""

    def collect_rows(self, client: PlayHQClient, org_id: str) -> list[dict[str, Any]]:
        """Traverse organisation → seasons → grades → grade fixture and map each game to a row."""
        rows: list[dict[str, Any]] = []
        for season in client.get_all(_SEASONS.format(org=org_id)):
            s_id, s_name = _pick(season, "id"), _name(season)
            if not s_id:
                continue
            for grade in client.get_all(_GRADES.format(season=s_id)):
                g_id, g_name = _pick(grade, "id"), _name(grade)
                if not g_id:
                    continue
                for game in client.get_all(_FIXTURE.format(grade=g_id)):
                    row = _game_to_row(game, season=s_name, grade=g_name)
                    if row["HomeTeam"] or row["AwayTeam"]:   # skip empty/placeholder fixtures (byes)
                        rows.append(row)
        return rows

    def _batch(self) -> SyncBatch:
        client = self._client()
        client_factory_used = self._client_factory is not None
        org = "fixture-org" if client_factory_used and not self._org_id() else self._org_id()
        rows = self.collect_rows(client, org)
        ds = build_match_summary(rows, source_system=self.source_system)
        last = ds.matches[-1].source_ref if ds.matches else None
        return SyncBatch(dataset=ds, cursor=SyncCursor(self.source_system, last_ref=last,
                                                       last_seen_at=datetime.now(UTC)))

    def fetch_new(self, since: SyncCursor | None) -> SyncBatch:
        # a full traversal; the import pipeline de-duplicates by source_ref, so re-polling never doubles
        return self._batch()

    def fetch_updated(self, since: SyncCursor | None) -> SyncBatch:
        # the same traversal surfaces changed results; the pipeline's updated-scorecard path handles them
        return self._batch()
