"""Internet Research Engine orchestration.

Ties the pieces together for one investigation: generate search queries from the job's natural-language
subject + structured context, discover candidate source URLs (via free, no-key providers), then fetch
each page through the SSRF-hardened client, extract a cricket candidate, and persist it as a reviewable
finding with full provenance. The run is *resumable*: progress lives in the job's checkpoint (frontier /
visited / counters), so an interrupted investigation continues rather than restarts, and it honours
pause/cancel between pages.

Nothing here writes to official statistics. Findings are evidence for a human to review; acceptance
still flows through the existing reconstruction + Phase 7 approval workflow. All fetched content is
untrusted data — it is extracted from, never executed or treated as instructions.

Discovery providers are deliberately free and key-optional:
  * Wikipedia OpenSearch (no key, public programmatic API) — always available.
  * Trove newspaper search (reuses :mod:`trove`) — only when a Trove API key is configured.
A workspace's own seed URLs and paid providers can be layered in later without changing this core.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy.engine import Connection

from onestats.core.config import Settings
from onestats.domain.research import classify, jobs, webextract, webfetch
from onestats.domain.research.webfetch import Fetcher

# A discovery provider: (queries, context) -> list of {"url", "source"} candidates.
Discovery = Callable[["list[str]", "dict[str, Any] | None"], "list[dict[str, str]]"]

_WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"


def generate_queries(query: str, context: dict[str, Any] | None) -> list[str]:
    """Build a small, de-duplicated set of search queries from the subject and context. Adds obvious
    cricket-scoped variants (club + season / competition) without inventing facts."""
    ctx = context or {}
    base = " ".join((query or "").split())
    out: list[str] = []
    if base:
        out.append(base)
    club = ctx.get("club") or ctx.get("team")
    season = ctx.get("season")
    competition = ctx.get("competition")
    opponent = ctx.get("opponent")
    if club and "cricket" not in base.lower():
        out.append(f"{club} cricket")
    if club and season:
        out.append(f"{club} cricket {season}")
    if club and opponent:
        out.append(f"{club} v {opponent} cricket")
    if competition and season:
        out.append(f"{competition} {season}")
    # de-dup preserving order, cap to keep runs bounded
    seen: set[str] = set()
    uniq: list[str] = []
    for q in out:
        k = q.lower().strip()
        if k and k not in seen:
            seen.add(k)
            uniq.append(q)
    return uniq[:6]


def discover_wikipedia(queries: list[str], context: dict[str, Any] | None, *,
                       fetcher: Fetcher, per_query: int = 5) -> list[dict[str, str]]:
    """Wikipedia OpenSearch: free, no key, intended for programmatic use. Returns article URLs."""
    out: list[dict[str, str]] = []
    for q in queries:
        url = (f"{_WIKIPEDIA_API}?action=opensearch&format=json&limit={per_query}"
               f"&namespace=0&search={_q(q)}")
        r = fetcher.fetch(url, _robots_check=False)  # public API endpoint; not a crawlable page
        if not r.ok or not r.text:
            continue
        try:
            data = json.loads(r.text)
        except (ValueError, TypeError):
            continue
        if isinstance(data, list) and len(data) >= 4 and isinstance(data[3], list):
            for link in data[3]:
                if isinstance(link, str) and link:
                    out.append({"url": link, "source": "wikipedia"})
    return out


def discover_trove(queries: list[str], context: dict[str, Any] | None, *,
                   settings: Settings) -> list[dict[str, str]]:
    """Trove historical newspapers — only if a key is configured (else yields nothing, never fabricates)."""
    if not getattr(settings, "trove_api_key", None):
        return []
    from onestats.domain.research import trove
    ctx = context or {}
    yr = ctx.get("year")
    out: list[dict[str, str]] = []
    for q in queries[:2]:
        try:
            res = trove.search_newspapers(settings, query=q, year_from=yr, year_to=yr, n=5)
        except Exception:  # noqa: BLE001 - a discovery provider failing must not abort the whole run
            continue
        for art in res.get("results", []):
            if art.get("url"):
                out.append({"url": art["url"], "source": "trove"})
    return out


def _q(s: str) -> str:
    from urllib.parse import quote
    return quote(s, safe="")


def default_discovery(settings: Settings, *, fetcher: Fetcher) -> Discovery:
    """The built-in discovery strategy (Wikipedia always; Trove when a key exists)."""
    def _discover(queries: list[str], context: dict[str, Any] | None) -> list[dict[str, str]]:
        found = discover_wikipedia(queries, context, fetcher=fetcher)
        found += discover_trove(queries, context, settings=settings)
        # de-dup by url, preserve order
        seen: set[str] = set()
        uniq: list[dict[str, str]] = []
        for c in found:
            if c["url"] not in seen:
                seen.add(c["url"])
                uniq.append(c)
        return uniq
    return _discover


def _page_fetcher(settings: Settings) -> Fetcher:
    ua = getattr(settings, "research_user_agent", None) or webfetch.DEFAULT_USER_AGENT
    # Accept HTML/text AND PDF (a common format for annual reports, handbooks and archived scorecards).
    return Fetcher(user_agent=ua, respect_robots=True,
                   allowed_content_types=(*webfetch.ALLOWED_CONTENT_TYPES, webfetch.PDF_CONTENT_TYPE))


def _discovery_fetcher(settings: Settings) -> Fetcher:
    """A fetcher that also accepts JSON (for discovery APIs). Still SSRF-hardened; robots is bypassed only
    for the explicit programmatic API endpoints we call."""
    ua = getattr(settings, "research_user_agent", None) or webfetch.DEFAULT_USER_AGENT
    return Fetcher(user_agent=ua, respect_robots=True,
                   allowed_content_types=(*webfetch.ALLOWED_CONTENT_TYPES, "application/json"))


def _host(url: str) -> str | None:
    try:
        return urlsplit(url).hostname
    except ValueError:
        return None


def run_step(conn: Connection, workspace_id: UUID, actor: str, job: dict[str, Any], *,
             settings: Settings, page_fetcher: Fetcher | None = None,
             discovery: Discovery | None = None) -> dict[str, Any]:
    """Process one bounded slice of the investigation and checkpoint. Returns
    ``{"done": bool, "processed": int, "new_findings": int, "examined": int, "findings": int}``.

    The worker calls this repeatedly, heartbeating and re-checking pause/cancel between calls, until
    ``done`` is True. Idempotent and resumable: all state is in the job checkpoint."""
    depth = job.get("depth") or "standard"
    budget = jobs.DEPTH_BUDGET.get(depth, jobs.DEPTH_BUDGET["standard"])
    cp = dict(job.get("checkpoint") or {})
    frontier: list[str] = list(cp.get("frontier") or [])
    visited: set[str] = set(cp.get("visited") or [])
    hashes: set[str] = set(cp.get("content_hashes") or [])
    examined = int(cp.get("examined") or 0)
    findings = int(cp.get("findings") or 0)

    page_fetcher = page_fetcher or _page_fetcher(settings)
    context = job.get("context") or {}

    # Seed the frontier once (first step).
    if not cp.get("seeded"):
        disc = discovery or default_discovery(settings, fetcher=_discovery_fetcher(settings))
        queries = generate_queries(job.get("query") or "", context)
        candidates = disc(queries, context)
        frontier = [c["url"] for c in candidates]
        cp["seeded"] = True
        cp["queries"] = queries
        jobs.save_checkpoint(conn, job["id"],
                             {**cp, "frontier": frontier, "visited": [], "content_hashes": [],
                              "examined": 0, "findings": 0},
                             progress={"phase": "searching", "queries": len(queries),
                                       "candidates": len(frontier), "sources_examined": 0, "findings": 0})

    processed = 0
    new_findings = 0
    # Load the workspace's match index once per step so each match-like finding can be classified
    # (possible_duplicate / additional_evidence / new) against existing records — review-only, never merged.
    match_index = classify.load_match_index(conn, workspace_id)
    while frontier and processed < jobs.STEP_BATCH and examined < budget:
        url = frontier.pop(0)
        if url in visited:
            continue
        visited.add(url)
        processed += 1

        r = page_fetcher.fetch(url)
        jobs.record_fetch(conn, workspace_id, job["id"], url=url, outcome=r.outcome,
                          http_status=r.http_status, content_type=r.content_type, nbytes=r.bytes,
                          content_sha256=r.content_sha256, detail=r.detail)
        examined += 1
        if not r.ok:
            continue
        if r.content_sha256 and r.content_sha256 in hashes:
            jobs.record_fetch(conn, workspace_id, job["id"], url=url, outcome=webfetch.DUPLICATE,
                              content_sha256=r.content_sha256, detail="identical content already seen")
            continue
        if r.content_sha256:
            hashes.add(r.content_sha256)

        # Choose the text source by content type: PDFs are read with pdfplumber, everything else is HTML/text.
        if r.content_type == webfetch.PDF_CONTENT_TYPE:
            page_text, is_html = webextract.pdf_to_text(r.content or b""), False
        else:
            page_text, is_html = (r.text or ""), True
        if not page_text.strip():
            continue

        ex = webextract.extract(r.final_url or url, page_text, is_html=is_html, context=context)
        if not ex.cricket_relevant:
            continue
        # Classify match-like findings against existing records (review-only; never merges).
        classification = "unknown"
        candidate = dict(ex.candidate)
        if ex.kind in classify.MATCH_KINDS:
            verdict = classify.classify(ex.candidate, match_index)
            classification = verdict["classification"]
            candidate["classification_reason"] = verdict["reason"]
            if verdict["candidate_match_ids"]:
                candidate["candidate_match_ids"] = verdict["candidate_match_ids"]
        fid = jobs.record_finding(
            conn, workspace_id, job["id"], url=r.final_url or url, kind=ex.kind,
            classification=classification, confidence=ex.confidence, title=ex.title, summary=ex.summary,
            source_host=_host(r.final_url or url), extracted=candidate, raw_excerpt=ex.raw_excerpt,
            content_sha256=r.content_sha256,
        )
        if fid is not None:
            findings += 1
            new_findings += 1

    done = not frontier or examined >= budget
    phase = "complete" if done else "searching"
    jobs.save_checkpoint(conn, job["id"],
                         {**cp, "frontier": frontier, "visited": sorted(visited),
                          "content_hashes": sorted(hashes), "examined": examined, "findings": findings},
                         progress={"phase": phase, "sources_examined": examined, "findings": findings,
                                   "candidates_remaining": len(frontier)})
    return {"done": done, "processed": processed, "new_findings": new_findings,
            "examined": examined, "findings": findings}
