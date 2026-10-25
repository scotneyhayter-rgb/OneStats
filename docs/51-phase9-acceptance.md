# Phase 9 — OneStats AutoSync: Manual Acceptance Checklist & Completion Report

For a reviewer in the **OneStats Sandbox** workspace. AutoSync is reached from **Club Management →
AutoSync** (`/manage/autosync`). Start the backend + desktop app (see [46](46-phase7-acceptance.md)).

## Consolidated test results (last run)

| Suite | Result |
|---|---|
| Backend (pytest) | **436 passing, 2 skipped** (DB tests roll back) |
| Desktop (vitest) | **56 passing**; `tsc` clean; `vite build` OK |
| Ruff | clean |
| Regression | CricketStatz (28) + all Phase 8 import tests green |

New Phase 9 coverage: background job engine (create/claim/heartbeat/checkpoint/retry/cancel,
restart reconciliation, duplicate prevention, isolation), source registry + connector catalog +
fixture connector, discovery (classification, new/updated, coverage, review queue, accept/reject/
bulk, source-failure-as-health), orchestration (Sync Now, historical discovery + resume, dashboard),
API wiring/auth, worldwide formats, and the AutoSync page.

## Honest scope of live sources

AutoSync is **fully operational against a deterministic fixture source** — it discovers, classifies,
queues, imports (as draft) and (in authorised mode) approves + recalculates, end to end. **No
verified live third-party connector ships in this phase.** PlayHQ, Play-Cricket and CricketArchive are
registered as **interface-only** connectors: they carry metadata but **refuse to fetch** (nothing is
fabricated), pending official API access / credentials / licensed sample data. Item 16 below is
performed only where legitimate live access is confirmed; otherwise it is documented, not simulated.

## Checklist

1. **Configure AutoSync.** AutoSync → Sources → add a source from a connector; enable it.
2. **Sync Now.** Click **Sync Now** on a source; confirm it runs a real job (status succeeds) and the
   dashboard counts update from the database (no fabricated numbers).
3. **Discover a new match.** Confirm discovered matches appear in the review queue classified **new**.
4. **Updated scorecard.** When a source reports a change to a known match, confirm an
   **updated-scorecard** item appears with the proposed change — the approved scorecard is unchanged.
5. **Prevent duplicate imports.** Re-run discovery; confirm no duplicate matches and that an existing
   fixture is classified **existing** / **possible duplicate**, never silently merged.
6. **Resolve ambiguous identities.** Confirm possible-duplicate / ambiguous items wait for your
   decision (accept / reject); names are never auto-merged.
7. **Preserve approved scorecards.** Approve a match, then have the source change it; confirm the
   change sits in the queue (classified **conflicting**) and the approved statistics are preserved.
8. **Historical discovery.** Run **Discover History** over a set of scopes; confirm coverage records
   each scope, and that an interrupted run resumes rather than restarts.
9. **Preserve incomplete evidence.** Confirm partial records and multiple sources per match are kept
   (Sources & Provenance on the match), and only approved scorecards feed official statistics.
10. **Bulk review.** Select several queued items and **Accept**/**Reject** in bulk; confirm each keeps
    its own provenance and audit.
11. **Recover after interruption.** Simulate a shutdown mid-job (or stop the app); on restart,
    confirm the job is **not** falsely "running" — it is reconciled (requeued) and resumes.
12. **Offline catch-up.** After the PC is off, confirm missed checks are picked up when the app runs.
13. **Source health.** Confirm an access failure marks the source **degraded/down** and records
    **failed** coverage — never "searched, no matches".
14. **Discovery provenance.** From a discovery, trace to its source evidence.
15. **Workspace isolation.** Confirm all AutoSync data is confined to the Sandbox workspace.
16. **A verified live connector** — only where legitimate access is available; otherwise documented
    as interface-only above.

## Requirements coverage

- **9.1** job engine ✅ · **9.2** source registry + connectors ✅ (live connectors interface-only) ·
  **9.3** settings/onboarding ✅ (AutoSync page sources config) · **9.4** historical discovery +
  coverage ✅ · **9.5** new-match discovery + classification ✅ · **9.6** updated-scorecard detection
  (never overwrites approved) ✅ · **9.7** identity/club/competition resolution (reuses existing;
  no auto-merge) ✅ · **9.8** review + authorised + bulk ✅ · **9.9** partial records + multiple
  sources ✅ · **9.10** offline catch-up, recovery, source health ✅ · **9.11** dashboard ✅ (real
  data, real Sync Now) · **9.12** worldwide formats; classification never inferred ✅ · **9.13**
  controlled concurrency (SKIP LOCKED), retry/backoff, credentials-ref-only, audit, duplicate-job
  prevention ✅ (full rate-limit tuning per live connector is per-connector work) · **9.14** future
  integration via the Phase 7 ledger + preserved provenance/dismissal data ✅ (later phases not built)
  · **9.15** comprehensive automated tests (deterministic fixtures) ✅ · **9.16** this document ✅.

## Limitations & external dependencies

- **No live third-party connector is verified in this phase** — all discovery runs against fixture
  sources. Adding PlayHQ / Play-Cricket / CricketArchive requires official API access, credentials or a
  licensed dataset, plus a verified sample to build and test the connector. These are documented
  interfaces, never claimed to work.
- Per-connector **rate limits / backoff tuning** and secure credential vault integration are finalised
  when a real connector is enabled.
- The in-process desktop job runner covers the Windows desktop; a cloud-hosted runner reuses the same
  interfaces (not built here).

**Phase 9: implementation + automated tests complete — awaiting user acceptance. Do not begin Phase 10
until Phase 9 is accepted.**
