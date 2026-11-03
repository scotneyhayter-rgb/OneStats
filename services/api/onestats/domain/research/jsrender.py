"""Optional JavaScript rendering for pages whose content is built client-side (Internet Research Engine).

Most cricket archives and newspaper pages are server-rendered and read fine via plain HTTP, so this is a
LAST-RESORT fallback used only on Deep searches for pages that come back near-empty. It is:

  * OFF by default and opt-in — enabled only when ``ONESTATS_RESEARCH_JS=1`` AND Playwright (with a
    browser) is actually installed. The packaged desktop sidecar does not ship a browser, so there it
    simply stays unavailable and the engine keeps using the plain SSRF-hardened fetch.
  * SSRF-screened before launching: the URL's host must pass the same public-IP-only validation as the
    normal fetcher. (Residual note: a full browser manages its own redirects/subresources, so this is
    deliberately gated off by default; pinned-IP navigation is a later hardening.)
  * Fail-closed and graceful: any missing dependency, disabled flag, blocked host or runtime error
    returns ``None`` and the caller falls back — it never raises into the worker.

Fetched/rendered HTML is untrusted data: it is extracted from, never executed as instructions.
"""
from __future__ import annotations

import logging
import os

from onestats.domain.research import webfetch

log = logging.getLogger("onestats.research.jsrender")

DEFAULT_TIMEOUT_MS = 15000


def enabled() -> bool:
    """True only when explicitly opted in AND Playwright is importable."""
    if os.environ.get("ONESTATS_RESEARCH_JS", "0") != "1":
        return False
    try:
        import playwright  # noqa: F401
    except Exception:  # noqa: BLE001 - not installed → unavailable
        return False
    return True


def render(url: str, *, resolver: "webfetch.Resolver | None" = None,
           user_agent: str = webfetch.DEFAULT_USER_AGENT, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> str | None:
    """Return the JS-rendered HTML for ``url``, or ``None`` if disabled/unavailable/blocked/failed."""
    if not enabled():
        return None
    chk = webfetch.validate_url(url, resolver=resolver)
    if not chk.ok:
        return None
    try:
        from playwright.sync_api import sync_playwright
    except Exception:  # noqa: BLE001 - defensive; enabled() already checked
        return None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page(user_agent=user_agent)
                page.goto(url, wait_until="networkidle", timeout=timeout_ms)
                return page.content()
            finally:
                browser.close()
    except Exception as exc:  # noqa: BLE001 - any Playwright/runtime error → graceful fallback
        log.info("JS render unavailable for %s: %s", url, type(exc).__name__)
        return None
