"""International import source policy — the agreed allow-list and accuracy rules (Parts D–G).

This is the single, authoritative definition of WHICH sources the autonomous importer may fetch, and
the accuracy guarantees every imported scorecard must satisfy. The import adapters (built on the shared
research engine) consult this module; it does no fetching itself.

Policy decided with the user:
  * Explicit allow-list only — the engine fetches ONLY the hosts marked ``fetchable`` here. No open
    crawl, and nothing is fetched just because a page links to it.
  * Bot-blocked / proprietary sites are NOT scraped. ESPNcricinfo actively blocks automated access
    (HTTP 403 at its edge) and its data is proprietary; it — like CricketStatz — is a ``benchmark``:
    a human looks things up there and we reconcile against it, but the engine never fetches it. We do
    not evade bot-detection, paywalls or auth.
  * Completeness needs corroboration: an expected count or a "complete" claim requires agreement across
    at least :data:`MIN_SOURCES_FOR_COMPLETENESS` sources. A single site is never treated as proof.
  * Accuracy over coverage: a scorecard is only as trustworthy as its evidence. Confidence is recorded
    as a number or left unknown (never silently zero); conflicting values between sources are flagged
    to the approval queue, never auto-resolved; a verified scorecard is never overwritten by
    lower-quality data; re-import reconciles to the existing match (stable ids), never duplicates.
  * Fetched bytes are DATA, never instructions (prompt-injection hardening), and robots/rate limits are
    honoured by the engine's fetch layer.
"""
from __future__ import annotations

from dataclasses import dataclass

# Agreement across at least this many independent sources is required before a coverage total is
# recorded as "expected" or a format/period is called complete. (Mirrors match_index.set_expected.)
MIN_SOURCES_FOR_COMPLETENESS = 2


@dataclass(frozen=True)
class Source:
    """One source and the role it plays.

    role:
      * ``fetchable`` — the engine MAY retrieve this host (open licence, machine-readable, bot-friendly).
      * ``benchmark`` — a human-consulted cross-check only; the engine must NOT fetch it.
    """
    key: str
    name: str
    host: str | None           # the registrable host the engine matches against; None for an offline benchmark
    role: str                  # "fetchable" | "benchmark"
    licence: str
    access: str                # how it is accessed (bulk download, API, manual lookup, local import)
    use_for: str               # what it is trusted to supply


# The allow-list. Order is informative, not significant.
SOURCES: tuple[Source, ...] = (
    Source("cricsheet", "Cricsheet", "cricsheet.org", "fetchable",
           "open data (freely downloadable, attribution requested)", "bulk JSON/CSV download",
           "ball-by-ball scorecards for Tests / ODIs / T20Is — the primary structured-data source"),
    Source("wikipedia", "Wikipedia / Wikidata", "wikipedia.org", "fetchable",
           "CC BY-SA", "MediaWiki / Wikidata API",
           "the match index (which matches exist), series lists, and team/player identity"),
    Source("wikidata", "Wikidata", "wikidata.org", "fetchable",
           "CC0", "Wikidata API",
           "stable cross-source identifiers for teams, players and grounds"),
    Source("espncricinfo", "ESPNcricinfo", None, "benchmark",
           "proprietary (bot-blocked; not scraped)", "manual lookup by a person",
           "human cross-check of scorecards and match facts — reconciled against, never fetched"),
    Source("cricketstatz", "CricketStatz", None, "benchmark",
           "proprietary (user's own licensed data)", "local import / manual lookup",
           "the trusted numerical benchmark to reconcile against — never overwritten"),
)

_BY_KEY = {s.key: s for s in SOURCES}


def fetchable_sources() -> tuple[Source, ...]:
    """The sources the engine is permitted to retrieve."""
    return tuple(s for s in SOURCES if s.role == "fetchable")


def benchmark_sources() -> tuple[Source, ...]:
    """Human-consulted cross-checks the engine must never fetch."""
    return tuple(s for s in SOURCES if s.role == "benchmark")


def _norm_host(host: str) -> str:
    h = host.strip().lower()
    if "://" in h:
        h = h.split("://", 1)[1]
    h = h.split("/", 1)[0].split(":", 1)[0]
    return h.removeprefix("www.")


def is_fetchable(host: str) -> bool:
    """Whether ``host`` (or a subdomain of one) is on the fetch allow-list. The engine's fetch layer
    calls this before any retrieval — a host that is not allow-listed is refused, so neither a link in
    fetched content nor a benchmark site can pull the importer off the agreed list."""
    if not host:
        return False
    h = _norm_host(host)
    for s in fetchable_sources():
        assert s.host is not None  # fetchable sources always carry a host
        if h == s.host or h.endswith("." + s.host):
            return True
    return False


def get_source(key: str) -> Source | None:
    return _BY_KEY.get(key)
