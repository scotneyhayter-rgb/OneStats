# OneStats — Development Dashboard

Lightweight, evidence-based status. Updated by hand from verified test/build runs — **no invented
completion percentages**. Full assessment: [43. Testing & Acceleration](43-testing-and-acceleration.md).

_Last updated: 2026-10-25 · branch `phase-2-foundation` · migration head `0033_stat_contributions`._

## Verified test evidence (last run)
| Suite | Result | Command |
|---|---|---|
| Backend (pytest) | **360 tests passing, 2 skipped** (DB tests roll back) | `run-tests.cmd backend` |
| Desktop (vitest) | **52 tests passing**; `tsc` clean; `vite build` OK | `run-tests.cmd desktop` |

The 2 skipped backend tests are `test_auth_service.py::test_bootstrap_creates_super_admin_with_valid_token`
and `::test_bootstrap_rejects_bad_token` — they exercise first-super-admin bootstrap, which only runs
when no super-admin exists. The dev DB already has one (`setup_required()` is False), so they skip by
design; the logic runs and is covered on a fresh DB (e.g. CI). Not a gap.

## Phase 7 — Validation, Integrity & Automatic Scorecard Intelligence — ✅ ACCEPTED (UAT complete 2026-10-25)

Manual acceptance (12-test checklist, [46](46-phase7-acceptance.md)) completed in the Sandbox: Tests
1–11 confirmed by the user; Test 12 (workspace isolation) is enforced by FORCE RLS and covered by
automated isolation tests. Defects found during acceptance were fixed and re-tested:

| Fix | Commit |
|---|---|
| Import CricketStatz captains & wicketkeepers (per match; both-roles; backfill) | `1955540` |
| Import CricketStatz toss winner (home/away code; decision left unknown) | `a1e8afd` |
| FOW/partnership batter selectors always offer this innings' batters (fill-ins); inline advisory highlights (decreasing FOW score, duplicate wicket, out-of-order/duplicate batter) | `dbe0479` |
| One-click "Confirm total" on the official-total bar (override preserved) | `deb0b3e` |
| Sentence-case the match Result dropdown options | `6169875` |
| Match date field no longer flashes/resets while editing (commit on blur) | `b6f7563` |
| Setting a competition's season rule back-fills existing matches' seasons | `54fa97e` |

## Phase 7 — stage implementation (all ✅ done)
| Stage | Status |
|---|---|
| 7.2 Automatic partnership generation (no button; on FOW/order/import change) | ✅ done |
| 7.3 Automatic match results & winning margins (+ recorded-vs-calculated conflict) | ✅ done |
| 7.4 Automatic season assignment (AU/calendar/UK/custom rules; manual preserved) | ✅ done |
| 7.7 Prominent innings score + Australian/English display | ✅ done |
| 7.5 Workspace-configurable match formats (enable/default/custom; history preserved) | ✅ done |
| 7.6 Historical team names & aliases (rename + source name; no auto-merge) | ✅ done |
| 7.1 Validation aggregation + Scorecard Approval workflow (draft/awaiting/approved/rejected) | ✅ done |
| 7.8 Automatic recalculation framework (approved-only, idempotent ledger) | ✅ done |
| 7.9 Import integrity (end-to-end preservation test) | ✅ done |
| 7.10 Comprehensive tests (360 backend + 52 desktop across all stages) | ✅ done |
| 7.11 Manual acceptance checklist ([46](46-phase7-acceptance.md)) | ✅ accepted (UAT complete) |
| Player-selector **club scoping** (fill-in discoverable) | ✅ done |

**Phase 7: implementation, automated tests AND user acceptance complete.**

**Known limitations (deferred to later phases, by scope):**
- **Run-out & wicket reconciliation** (bowling-summary run-out count, bowler-credited vs non-bowler
  totals, reconciliation) → **Phase 12** ([48](48-phase12-dismissal-reconciliation.md)). Phase 8
  retains all dismissal data it needs (raw code, mapped type, bowler, fielder); classification is
  verified in import regression tests.
- Competition **points/ladders** architecture exists (`playing_conditions`); the user-friendly
  Points Manager + ladder calc is a later phase.
- Full **statistics/records/milestones** reporting modules build on the 7.8 ledger (integration
  points provided; two calculators — player batting & bowling — ship now).
| Desktop type-check / build | **clean** | `cd apps\desktop && npm run build` |
| Native Tauri window | **manual only** (no automated coverage) | — |

## 18-phase tracker
| # | Phase | Status |
|---|---|---|
| 1 | Planning & Architecture | ✅ Complete |
| 2 | Desktop & Server Foundation | ✅ Complete |
| 3 | Workspaces, Onboarding & Permissions | ✅ Complete |
| 4 | Clubs, Associations & Competitions | ✅ Complete |
| 5 | People & Profiles | ✅ Complete |
| **6** | **Matches & Scorecard Entry** | **✅ Complete (manual entry + CricketStatz import accepted)** |
| **7** | **Validation, Integrity & Automatic Scorecard Intelligence** | **✅ Complete — user-accepted 2026-10-25** |
| **8** | **Universal Third-Party Import Framework** | **🔄 In progress — design ([47](47-phase8-import-framework.md)); authorised 2026-10-25** |
| 9–18 | AutoSync → … → RMCC Trial | ⏳ Future |

## Phase 6 stage detail
| Stage | Scope | Status |
|---|---|---|
| 1 Match core | 0018 | ✅ |
| 2 Innings & extras | 0019 | ✅ |
| 3 Batting & dismissals | 0020 | ✅ |
| 4 Bowling | 0021 | ✅ |
| 5 FOW & partnerships | 0022 | ✅ |
| 6 Finals linkage & premierships | 0023 | ✅ |
| **7 Manual scorecard entry UI** | — | **🔄 under testing** |
| 8 CricketStatz import | — | ⛔ gated (approval) |

## Stage 7 acceptance — verified vs outstanding
**Done & verified (automated):** scorecard editor (all sections); dropdown selection persists
(fixed `fc8ffe1`, DOM test); toss/captains/keepers + explicit batting team (`0024`); team-name
match list; visual refinement, responsive shell, Focus Mode, branding; **player participation &
attribution foundation** incl. the **Bill Smith** scenario (`0025`, `test_participation`).

**Outstanding (NOT built):**
- Automatic partnerships from Fall of Wickets (+ contribution model).
- Player **Wizard UI** (backend roster/transfer/fill-in endpoints are in place).
- Validation **categories** (Error / Warning / Incomplete / Verified).
- Batting-order management: **remove-batter** (code path looks correct — needs live repro),
  drag-and-drop + up/down reordering + renumber + confirm-on-stats.
- Auto-calc **display** (strike rate / economy / run rate) in the UI.

## Outstanding defects / notes
- Dev server can blank after import changes (Vite "504 Outdated Optimize Dep") → `rm -rf
  apps/desktop/node_modules/.vite` then restart. Not a code defect.
- Native Tauri behaviours (icon, title bar, window) are **manual-test only**.

## Ready-for-manual-testing
- ✅ Dropdown selection, participation/attribution (via synthetic seed), match/innings/batting/
  bowling/FOW/partnership entry, save & reopen.
- ⏳ Not ready (not built): auto-partnerships, Player Wizard UI, validation categories, batting-order
  tools.

## Open decisions
D-ACC-1 CI · D-ACC-2 next Stage-7 feature · D-ACC-3 Stage 8 (gated) · D-ACC-4 parallel worktrees.
See [43](43-testing-and-acceleration.md).
