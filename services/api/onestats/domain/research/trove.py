"""Historical newspaper search via Trove (National Library of Australia), v3 API.

Trove digitises Australian historical newspapers (e.g. the *Ararat Advertiser*) and offers a free
public API for non-commercial use. This module searches the newspaper zone and returns normalised
article hits — heading, newspaper, date, a text snippet and the link to the digitised page — so a
researcher can read the article and save it as a research **source**. It never fabricates match data:
discovery ends at the article link; transcription into a scorecard stays a deliberate human step.

A key is required (``ONESTATS_TROVE_API_KEY``). Without one, :func:`search_newspapers` raises
:class:`TroveError` with a clear message and fetches nothing. The HTTP client is injectable so the
whole path is testable against a recorded response without any network access or key.
"""
from __future__ import annotations

from typing import Any

from onestats.core.config import Settings


class TroveError(Exception):
    """A newspaper-search failure the API surfaces to the user (missing key, upstream error)."""


class TroveClient:
    """Thin httpx wrapper for the Trove v3 ``/result`` endpoint. httpx is imported lazily so the module
    loads without it (tests inject a fake client)."""

    def __init__(self, *, api_key: str, base_url: str) -> None:
        self._key = api_key
        self._base = base_url.rstrip("/")

    def result(self, params: list[tuple[str, Any]]) -> dict[str, Any]:
        import httpx

        headers = {"X-API-KEY": self._key, "Accept": "application/json"}
        resp = httpx.get(self._base + "/result", headers=headers, params=params, timeout=30.0)
        if resp.status_code in (401, 403):
            raise TroveError("The Trove API key was rejected — check it is correct and active.")
        resp.raise_for_status()
        return resp.json()


def _pick(d: Any, *keys: str) -> Any:
    if not isinstance(d, dict):
        return None
    for k in keys:
        v = d.get(k)
        if v not in (None, ""):
            return v
    return None


def _newspaper_name(article: dict[str, Any]) -> str | None:
    """The newspaper title, which v3 returns as a nested {id, value} object (or sometimes a string)."""
    t = article.get("title")
    if isinstance(t, str):
        return t
    return _pick(t, "value", "name")


def _decades_in_range(year_from: int | None, year_to: int | None) -> list[str]:
    """Trove scopes newspapers by decade facet (first three digits of the year, e.g. '190' = 1900s).
    Translate an inclusive year range into the decade facets that cover it."""
    if year_from is None and year_to is None:
        return []
    lo = year_from if year_from is not None else year_to
    hi = year_to if year_to is not None else year_from
    if lo is None or hi is None:
        return []
    if lo > hi:
        lo, hi = hi, lo
    return [str(d // 10) for d in range(lo - lo % 10, hi + 1, 10)]


def _parse(data: dict[str, Any]) -> dict[str, Any]:
    """Normalise a Trove v3 result into {total, results[]}. Defensive about field presence/shape."""
    categories = data.get("category")
    bucket: dict[str, Any] = {}
    if isinstance(categories, list):
        for c in categories:
            if isinstance(c, dict) and c.get("code") == "newspaper":
                bucket = c.get("records") or {}
                break
    articles = bucket.get("article") or []
    if not isinstance(articles, list):
        articles = []
    results = []
    for a in articles:
        if not isinstance(a, dict):
            continue
        results.append({
            "id": str(_pick(a, "id") or ""),
            "heading": _pick(a, "heading", "title") or "(untitled article)",
            "newspaper": _newspaper_name(a),
            "date": _pick(a, "date"),
            "page": _pick(a, "page"),
            "snippet": _pick(a, "snippet"),
            "url": _pick(a, "troveUrl", "identifier", "trovePageUrl", "url"),
        })
    total = bucket.get("total")
    try:
        total = int(total)
    except (TypeError, ValueError):
        total = len(results)
    return {"total": total, "results": results}


def search_newspapers(
    settings: Settings,
    *,
    query: str,
    year_from: int | None = None,
    year_to: int | None = None,
    newspaper_title: str | None = None,
    n: int = 20,
    client: TroveClient | None = None,
) -> dict[str, Any]:
    """Search Trove's digitised newspapers. Returns {query, total, results[], source}. Raises
    :class:`TroveError` when no key is configured or the upstream call fails."""
    q = (query or "").strip()
    if not q:
        raise TroveError("Enter something to search for.")
    if client is None:
        key = settings.trove_api_key
        if not key:
            raise TroveError(
                "No Trove API key is configured. Add a free key from trove.nla.gov.au "
                "(Me → For developers) to search historical newspapers."
            )
        client = TroveClient(api_key=key, base_url=settings.trove_base_url)

    # Optionally narrow the search text to a specific newspaper by name (Trove matches it in the query).
    full_q = f'{q} "{newspaper_title.strip()}"' if newspaper_title and newspaper_title.strip() else q
    params: list[tuple[str, Any]] = [
        ("q", full_q),
        ("category", "newspaper"),
        ("encoding", "json"),
        ("n", max(1, min(n, 100))),
        ("sortby", "dateasc"),
    ]
    for decade in _decades_in_range(year_from, year_to):
        params.append(("l-decade", decade))
    if year_from is not None and year_to is not None and year_from == year_to:
        params.append(("l-year", str(year_from)))

    try:
        data = client.result(params)
    except TroveError:
        raise
    except Exception as exc:  # noqa: BLE001 — upstream/network error surfaced cleanly
        raise TroveError(f"Could not reach Trove: {exc}") from exc

    out = _parse(data)
    out["query"] = q
    out["source"] = "Trove (National Library of Australia)"
    return out
