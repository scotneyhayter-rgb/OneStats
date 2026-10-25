# Phase 9 — OneStats AutoSync: Final Handover & Acceptance Report

**Status: CONDITIONALLY ACCEPTED — 2026-10-25.**
Accepted by the user with one outstanding external dependency (the live PlayHQ connector, Test 16).

This report is the formal close-out of Phase 9. It records what was accepted, what remains blocked,
how credentials are protected, and exactly how to finish the one outstanding test when access is
obtained. It also confirms Phase 9 has no other unresolved defects and that Phase 10 can proceed
independently of PlayHQ access.

Related documents: acceptance checklist [51](51-phase9-acceptance.md); external dependency register
[52](52-phase9-external-dependencies.md); AutoSync plan [50](50-phase9-autosync-plan.md).

---

## 1. Acceptance summary

| Item | Outcome |
|---|---|
| Phase 9 overall | **Conditionally accepted (2026-10-25)** |
| Manual acceptance Tests 1–15 | **PASSED** (Sandbox workspace, built-in fixture sources) |
| Test 16 — live PlayHQ connector | **BLOCKED — not passed** (external dependency: valid approved PlayHQ API Client ID) |
| PlayHQ / Play-Cricket / CricketArchive connectors | **Interface-only — not operational** (carry metadata, refuse to fetch) |
| Automated tests | Backend **440 passed, 2 skipped**; desktop **56 passed**; `tsc` clean; ruff clean |
| Other outstanding Phase 9 defects | **None** |
| Phase 10 dependency on PlayHQ | **None** — Phase 10 proceeds independently |

Tests 1–15 verified: AutoSync configuration; Sync Now running a real job with DB-backed counts;
new-match discovery; updated-scorecard detection (approved scorecard untouched); duplicate prevention;
ambiguous-identity hold (no auto-merge); approved-scorecard preservation on conflict; historical
discovery with resume; partial records + multiple sources per match; bulk review; interruption
recovery; offline catch-up; source-health on failure; discovery provenance; workspace isolation.

## 2. What is implemented vs tested vs outstanding

- **Implemented and tested (against deterministic fixtures):** the background job engine
  (`onestats/domain/autosync/jobs.py`), source registry + connector catalog
  (`sources.py`, `connectors.py`), discovery/classification/review/coverage (`discovery.py`),
  orchestration — Sync Now, historical discovery with resume, startup reconciliation, dashboard
  (`service.py`), the API surface (`api/v1/autosync.py`, gated by `import.manage`), and the AutoSync
  page (`apps/desktop/src/features/autosync/AutoSync.tsx`). Migrations 0034–0037 (all FORCE RLS,
  additive). The whole pipeline — discovery → review → import (as draft) → approval → recalculation —
  runs end-to-end against the two clearly-labelled built-in fixture sources (`onestats_sample`,
  `onestats_sample_news`).
- **Implemented but NOT tested against live data:** the live-source connector *interfaces* for PlayHQ,
  Play-Cricket and CricketArchive. These are registered as **interface-only** — they carry provider
  metadata but **refuse to fetch**, so nothing is fabricated and none is claimed to work.
- **Outstanding (external dependencies):** a verified live connector. PlayHQ is blocked on a valid,
  approved API Client ID; Play-Cricket on an ECB API key + site permission + sample; CricketArchive on
  a commercial licence + sample. See [52](52-phase9-external-dependencies.md).

## 3. PlayHQ — the one outstanding dependency (Test 16)

All inputs except the credential are verified and ready:

- Base `https://api.playhq.com`; headers `x-api-key` (36-char UUID Client ID) + `x-phq-tenant`.
- Tenant **`ca`** (cricket) confirmed.
- Target organisation id **`2a9c6833-92cb-466b-aea8-16fa8277887d`** (Rhymney/Moyston) confirmed.
- Endpoint chain org → seasons → grades → fixtures → games and cursor pagination confirmed.

**Blocker:** the key supplied during acceptance was 28 characters and returned **HTTP 401 "Client ID is
Invalid"**. A valid PlayHQ Client ID is a 36-char UUID, issued via a PlayHQ support request and approved
by PlayHQ and Cricket Australia (not self-serve). Until a valid key is held, the PlayHQ connector stays
interface-only and **must not be marked operational**.

**Steps to complete Test 16 when a valid key is available** are documented in
[52 → "Completing Test 16"](52-phase9-external-dependencies.md): place the key in the gitignored
`services/api/.env` as `ONESTATS_PLAYHQ_API_KEY`, smoke-test auth (expect 200), build the live
`PlayHqConnector` against a captured real response, add connector tests against that sample, run Test 16
end-to-end in the Sandbox, and only then mark it passed and flip the register to operational.

## 4. Credential protection (verified 2026-10-25)

- `services/api/.env` is **gitignored** (`.env`, `.env.*`, with `!.env.example`) and **untracked** — no
  secret is in version control.
- No key value appears in any tracked file (scanned); no key assignment is committed.
- The interface-only connector does not read or log the key; nothing logs `x-api-key`.
- `services/api/.env.example` carries only a **commented placeholder** for `ONESTATS_PLAYHQ_API_KEY`
  (no value) so operators know the variable exists.
- The running backend log contains no key material.
- Config (`onestats/core/config.py`) reads the key from env/`.env` only (`ONESTATS_` prefix); the
  registry stores a credential **reference**, never the secret.

> Note: a candidate key string was pasted into chat during acceptance. It is invalid for PlayHQ, but if
> it is a live credential for any other system it should be **rotated/revoked**.

## 5. Known limitations (carried forward)

- No verified live third-party connector ships in Phase 9; all discovery runs against fixtures.
- Per-connector rate-limit / backoff tuning and secure credential-vault integration are finalised when a
  real connector is enabled.
- The in-process desktop job runner covers the Windows desktop; a cloud-hosted runner would reuse the
  same interfaces (not built in this phase).

## 6. Readiness for Phase 10

Phase 10 (Historical Research Centre) **does not depend on PlayHQ credentials**. It builds on the
accepted Phase 6 scorecard model, Phase 7 validation/approval, Phase 8 Universal Import + CCDM, and the
Phase 9 AutoSync discovery/provenance interfaces — all of which are complete and tested against
fixtures. Historical research development is not gated by live third-party access.

---

**Phase 9: conditionally accepted. Test 16 remains explicitly blocked (not passed) pending a valid,
approved PlayHQ API Client ID. No other Phase 9 defects outstanding.**
