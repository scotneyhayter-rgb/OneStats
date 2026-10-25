# Phase 9 — OneStats AutoSync (implementation plan)

_Prepared 2026-10-25. **Implementation is gated on formal Phase 8 user acceptance** (Phase 9 prompt
§2 / §7). This document is the plan only; no Phase 9 code is written until acceptance is recorded._

## Phase 8 acceptance gate — technical status

| Gate item | Status |
|---|---|
| Universal Import Framework operational | ✅ five adapters import through one pipeline (409 backend tests) |
| CricketStatz imports remain compatible | ✅ 28 regression tests green, behaviour unchanged |
| Adapter registry / CCDM / staging / matching / promotion / provenance | ✅ present and tested |
| Phase 7 approval + recalculation remain authoritative | ✅ imported matches draft; sync honours approval |
| Outstanding technical improvements are Phase 9 blockers? | ❌ none — CS staging convergence and batched-insert/streaming are documented non-blockers |
| Unresolved critical security / data-integrity defects? | ❌ none known (FORCE RLS isolation; defused XML; no fabrication) |
| **User has formally accepted Phase 8** | ⏳ **not yet recorded — the gate holds here** |

Everything technical is green; only the **formal user acceptance** of Phase 8 is outstanding. Stage
9.1 begins once that is confirmed.

## Architectural approach (extend, never compete)

AutoSync is **another controlled entry point into the Phase 8 pipeline**, built on the Stage 8.9
interfaces (`SyncSource`, `SyncCursor`, `SyncBatch`, `SyncJob`, `process_sync_batch`, modes
`review_required` / `authorised_automatic`). It reuses: workspaces + FORCE RLS, permissions, club/
team/competition models, person identity + aliases, the Phase 7 approval workflow and recalculation
ledger, the Phase 8 Canonical model, adapter registry, duplicate detection, provenance/import history
and resumable staging. **No competing database, approval system, statistics engine or matching
service.** Unknown stays unknown; nothing (players/scores/wickets/dismissals/captains/keepers/toss/
results) is ever fabricated.

### New, additive persistence (FORCE RLS, non-destructive migrations)

- `sync_source` — the source registry (§9.2 fields: provider, access method, endpoint, auth, coverage,
  formats, rate limits, reliability, last success, connector version, mapping).
- `sync_job` — persistent background jobs: workspace, source, kind (new/updated/historical), schedule,
  status, progress, checkpoint, lease/heartbeat, attempts, audit.
- `discovery_coverage` — per (workspace, source, competition/season/grade) periods classified as
  searched / partial / awaiting / no-accessible-source / failed (§9.4).
- `discovery_item` / review queue — discovered candidates with classification (new / existing /
  possible-duplicate / additional-evidence / conflicting / insufficient), source evidence, confidence.
- `source_health` — access/auth/parse/mapping failures, empty-result and rate-limit signals (§9.10).

## External-source reality (honesty requirement)

Real connectors are implemented **only when their access method and data structure are verified**
against legitimate, permitted access. No endpoints are invented; auth, paywalls and anti-bot controls
are never bypassed. **Expected initial state: no verified live connector** — PlayHQ, Play-Cricket,
state/domestic, First-Class and international sources require an official API, licensed feed,
authorised sample export, or permission not yet in hand. Therefore AutoSync ships **fully operational
against deterministic fixture sources** (a `SyncSource` backed by stored sample data, exercising the
whole discovery→import→approval→recalc path), with each real provider documented as an **interface
awaiting verified access**. A live connector is enabled and its acceptance step (§9.16.16) performed
**only where legitimate access is confirmed**, clearly distinguished from fixture testing.

## Staged plan (9.1–9.16)

- **9.1** AutoSync architecture + background job engine: persistent `sync_job`, per-workspace queue,
  schedules, progress/cancel, retry/checkpoint recovery, duplicate-job prevention, restart-safe
  (lease/heartbeat; on startup, reconcile jobs that were "running" when the PC powered off — never
  falsely reported running; missed checks detected and resumed). In-process desktop runner, no
  external broker; reusable interface for future cloud runner.
- **9.2** Source registry + connector contract; deterministic fixture connector(s); document each real
  provider's access dependency. Verified live connectors only where access is confirmed.
- **9.3** Workspace AutoSync settings + onboarding (simple defaults, advanced options; multiple source
  configs; continuity across club association/competition changes).
- **9.4** Discover Entire Workspace History — systematic search within configured, permitted scope;
  coverage classification (searched/partial/awaiting/no-source/failed); resumable; never claim a
  period verified just because a search returned nothing.
- **9.5** New match discovery + identification via the Phase 8 duplicate framework; classify discoveries;
  never silently merge or duplicate.
- **9.6** Updated-scorecard detection (checksums/normalised-content compare; distinguish data vs
  formatting changes); preserve versions; proposed changes reviewed; never silently overwrite an
  approved scorecard (Phase 7 revision/approval; last approved stats preserved until re-approval).
- **9.7** Identity/club/competition resolution — reuse person/team management + aliases; confidence +
  evidence; administrator review for ambiguity; no auto-merge on name similarity.
- **9.8** Automated import/review/approval — review-queue default; authorised-automatic for reliable
  sources + deterministic matches (import never becomes auto-approval); permission-controlled bulk
  review preserving provenance/validation/audit/approval/recoverability.
- **9.9** Partial records + multiple sources — provisional vs draft vs approved; multiple sources per
  match (R1) with conflicts; only approved scorecards feed official stats; no inference of missing
  figures; evidence accessible to Phase 10.
- **9.10** Offline catch-up, recovery + source health — resume after shutdown/restart/network/outage/
  auth/rate-limit; controlled catch-up; a failed search is never evidence that no matches exist.
- **9.11** AutoSync dashboard — real DB-backed status, Sync Now (triggers a real authorised job), last/
  next sync, sources, discoveries/updates/duplicates/review items/failures/warnings, coverage
  progress, provenance links. No fabricated counts.
- **9.12** Worldwide coverage — men's/women's/junior/senior/disability/ability-classified/club/
  association/representative/state/domestic/First-Class/List A/international; formats (Test/ODI/T20I/
  FC/List A/T20/Multi-Day/One-Day/custom); never assume men's; never infer classification from names;
  respect historical changes; strict per-workspace isolation.
- **9.13** Performance, security + cost control — rate limits, backoff, concurrency, timeouts, resource
  limits, duplicate-request prevention, secure credential storage, permission checks, audit, batching,
  checkpoints; no paid external services without authorisation; integration points for future
  billing (Phase 17) without building it.
- **9.14** Future-phase integration points (Research Centre / Statistics / Records / Ask OneStats /
  Publishing) via the Phase 7 ledger + preserved provenance and dismissal data; build none of those
  phases now.
- **9.15** Comprehensive automated tests (deterministic fixtures; no live-site dependency for routine
  tests) covering the full scenario list, plus CricketStatz + Phase 8 regression.
- **9.16** Manual acceptance checklist + consolidated completion report; live-source demonstration only
  where legitimate access exists, clearly distinguished from fixture testing.

## Non-negotiables carried throughout

No fabrication; unknown stays unknown; no auto-merge of uncertain identities; provenance + source
evidence preserved; approved scorecards never silently overwritten; Phase 7 approval/recalc remain
authoritative; FORCE RLS workspace isolation; additive migrations; no bypassing auth/paywalls/anti-bot;
no invented endpoints; no fabricated data implying a live integration works.
