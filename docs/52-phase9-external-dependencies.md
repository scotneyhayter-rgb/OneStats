# Phase 9 — External Integration Dependency Register

_Logged 2026-10-25 during Phase 9 acceptance. **No verified live connector is operational.** The
providers below are registered as **interface-only** connectors: they carry metadata but refuse to
fetch, so nothing is fabricated and none is claimed to work. A connector is implemented and enabled
only after the listed access is obtained and its real data structure is verified against a legitimate
sample._

| Provider | `connector_id` | Status | Access method | What is required to make it operational |
|---|---|---|---|---|
| **PlayHQ** | `playhq` | interface-only (not operational) | Official API | A PlayHQ **API account / partner access** and **credentials**, confirmation of the **terms of use** for automated retrieval, and a **legitimate sample export** (a few matches incl. scorecards) to verify endpoints, field names, nesting, and dismissal/result/identifier encodings. |
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
