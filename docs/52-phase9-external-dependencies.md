# Phase 9 — External Integration Dependency Register

_Logged 2026-10-25 during Phase 9 acceptance. **No verified live connector is operational.** The
providers below are registered as **interface-only** connectors: they carry metadata but refuse to
fetch, so nothing is fabricated and none is claimed to work. A connector is implemented and enabled
only after the listed access is obtained and its real data structure is verified against a legitimate
sample._

| Provider | `connector_id` | Status | Access method | What is required to make it operational |
|---|---|---|---|---|
| **PlayHQ** | `playhq` | interface-only (**not operational — key rejected**) | Official API (`https://api.playhq.com`) | **Blocker = a valid, approved PlayHQ API Client ID** (a 36-char UUID). **Verified 2026-10-25:** endpoints + auth confirmed (`x-api-key` + `x-phq-tenant`; org → seasons → grades → fixtures → games; cursor pagination); tenant **`ca`** confirmed; target org id **confirmed** as `2a9c6833-92cb-466b-aea8-16fa8277887d` (Rhymney/Moyston, from `ca.playhq.com/org/.../dashboard`). Two live calls (short id and full UUID) both returned **HTTP 401 "Client ID is Invalid"** — the supplied key (28 chars) is **not** a valid Client ID. PlayHQ Client IDs are issued via a PlayHQ support request, **reviewed/approved by PlayHQ and Cricket Australia**. Once a valid approved key is in `.env` (`ONESTATS_PLAYHQ_API_KEY`), the connector can be built against a live response, tested and enabled — all other inputs are ready. |
| **Play-Cricket (ECB)** | `play_cricket` | interface-only (not operational) | Official API | An **ECB Play-Cricket API key** and **site registration/permission**, plus a **sample response** from the site's API to verify the data structure and mappings. |
| **CricketArchive** | `cricket_archive` | interface-only (not operational) | Licensed feed | A **commercial licence / data agreement** for the historical dataset, agreed usage terms, and a **licensed sample** to build and test the adapter. |

## Rules (carried from the plan)

- No endpoints are invented; no authentication, paywall or anti-bot control is ever bypassed.
- A connector is **not** claimed to work until it has been **successfully tested against verified
  sample data**; until then it stays interface-only and cannot fetch.
- When a provider requires credentials or an agreement, that dependency is recorded here and a
  deterministic **fixture** source is used for development and testing instead.
- Each real connector, once enabled, needs its own **rate-limit / backoff** tuning and secure
  **credential storage** (the registry stores only a reference, never the secret).

## Current operational sources

- **OneStats sample (fixture)** and **OneStats sample newspaper (fixture)** — deterministic sample
  data, clearly labelled, **not live**. Used to exercise and accept the whole AutoSync pipeline
  (discovery → review → import → approval → recalculation) without external access.
