# Phase 9 — External Integration Dependency Register

_Logged 2026-10-25 during Phase 9 acceptance. Phase 9 was **conditionally accepted** on that date with
the items below as the outstanding external dependencies. **No verified live connector is operational.**
The providers below are registered as **interface-only** connectors: they carry metadata but refuse to
fetch, so nothing is fabricated and none is claimed to work. A connector is implemented and enabled
only after the listed access is obtained and its real data structure is verified against a legitimate
sample. **Acceptance Test 16 (live connector) is BLOCKED, not passed**, pending the access below._

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

## Completing Test 16 — PlayHQ live connector (when a valid key is available)

Everything except the credential is ready (org id, tenant, endpoint chain and pagination are verified).
When a **valid, approved 36-char UUID PlayHQ Client ID** is obtained, complete Test 16 like this:

1. **Place the key** in `services/api/.env` as `ONESTATS_PLAYHQ_API_KEY=<uuid>` (the file is gitignored;
   never commit it). `ONESTATS_PLAYHQ_TENANT` defaults to `ca`. Restart the backend so it reloads.
2. **Smoke-test auth** with one authenticated call to confirm the key is accepted (expect HTTP 200, not
   401): `GET https://api.playhq.com/v1/organisations/2a9c6833-92cb-466b-aea8-16fa8277887d` with headers
   `x-api-key: <uuid>` and `x-phq-tenant: ca`. Capture a sample response (store it outside source control).
3. **Build the live connector** `PlayHqConnector` in `services/api/onestats/domain/autosync/connectors.py`
   implementing the `fetch`/discovery contract (org → seasons → grades → fixtures → games; follow
   `metadata.hasMore` / `metadata.nextCursor` cursor pagination). Replace the `InterfaceOnlyConnector`
   registration for `playhq` with it **only when** a real response has been parsed successfully; map its
   fields into the Phase 8 CCDM so discovery/dedupe/import run unchanged. Add **rate-limit / backoff**
   tuning for the live endpoint; the registry stores only a credential **reference**, never the secret.
4. **Add connector tests** against the captured sample (as a fixture), mirroring the existing fixture
   connector tests — never against the live API in CI.
5. **Run acceptance Test 16** end-to-end in the Sandbox: add a PlayHQ source, Sync Now, confirm real
   discovery → review → import. Only then update [51](51-phase9-acceptance.md) to mark Test 16 passed and
   change this register's PlayHQ status from interface-only to operational.

Play-Cricket and CricketArchive follow the same pattern once their respective credentials/licence and a
verified sample are obtained.

## Current operational sources

- **OneStats sample (fixture)** and **OneStats sample newspaper (fixture)** — deterministic sample
  data, clearly labelled, **not live**. Used to exercise and accept the whole AutoSync pipeline
  (discovery → review → import → approval → recalculation) without external access.
