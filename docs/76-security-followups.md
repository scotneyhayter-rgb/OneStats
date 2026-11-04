# 76. Security Follow-ups (accepted known issues)

**Created 2026-11-03.** Tracked security items found in the pre-public-launch review of the Internet
Research Engine. Both are **accepted as known issues** for the first public release (user decision) —
the defaults make them low-risk — and are to be converted into GitHub issues once the repo is pushed.
Neither blocks going public. **Do not weaken any existing safety check when addressing these.**

## SEC-1 — DNS-rebinding TOCTOU in the research fetcher

- **Where:** `services/api/onestats/domain/research/webfetch.py` (`validate_host` / `Fetcher.fetch`).
- **Severity:** medium-low (PLAUSIBLE). Not exploitable by the common SSRF vectors, which are already
  blocked.
- **Issue:** the fetcher validates the hostname and collects the resolved public IPs, but the httpx
  client re-resolves the hostname at connect time rather than connecting to the already-vetted IP. A
  DNS-rebinding attacker who controls the target's DNS could return a public IP to our resolver (passes
  validation) and a private IP to the socket (the actual connection) — a time-of-check/time-of-use gap.
- **Already mitigated:** scheme allow-list, no auto-redirects (every hop re-validated), literal
  private/loopback/link-local/CGNAT/reserved targets blocked, `trust_env=False`, size/type/timeout caps.
  The residual is explicitly documented in the module header.
- **Fix approach:** pin the validated IP for the actual connection — connect to the vetted IP with the
  original `Host` header (and SNI) via a custom httpx transport / resolver, so check and use are the same
  address. Re-validate on each redirect hop as today.

## SEC-2 — Playwright subresource/redirect SSRF when JS rendering is enabled

- **Where:** `services/api/onestats/domain/research/jsrender.py`.
- **Severity:** low (PLAUSIBLE). Off by default; the packaged desktop sidecar ships no browser.
- **Issue:** when JS rendering is explicitly enabled (`ONESTATS_RESEARCH_JS=1` **and** a Playwright
  browser is installed), the real Chromium instance manages its own redirects and subresource requests
  (images, scripts, XHR) outside the SSRF-hardened fetch path. Only the initial navigation URL is
  screened, so a rendered page could cause the browser to reach internal resources.
- **Already mitigated:** disabled by default, requires an opt-in env flag plus an installed browser the
  shipped app does not include, and the initial URL host is validated. The residual is documented in the
  module header.
- **Fix approach:** when enabling JS rendering, route the browser through a validating proxy that applies
  the same public-IP-only check to every request, or pin/allow-list the navigation and block
  cross-origin subresources; keep it opt-in.
