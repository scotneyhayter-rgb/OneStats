# OneStats — Development Dashboard

Lightweight, evidence-based status. Updated by hand from verified test/build runs — **no invented
completion percentages**. Full assessment: [43. Testing & Acceleration](43-testing-and-acceleration.md).

_Last updated: 2026-10-25 · branch `phase-2-foundation` · migration head `0032_scorecard_approval`._

## Verified test evidence (last run)
| Suite | Result | Command |
|---|---|---|
| Backend (pytest) | **348 tests passing, 2 skipped** (DB tests roll back) | `run-tests.cmd backend` |
| Desktop (vitest) | **42 tests passing**; `tsc` clean; `vite build` OK | `run-tests.cmd desktop` |

## Phase 7 — Validation, Integrity & Automatic Scorecard Intelligence (in progress)
| Stage | Status |
|---|---|
| 7.2 Automatic partnership generation (no button; on FOW/order/import change) | ✅ done |
| 7.3 Automatic match results & winning margins (+ recorded-vs-calculated conflict) | ✅ done |
| 7.4 Automatic season assignment (AU/calendar/UK/custom rules; manual preserved) | ✅ done |
| 7.7 Prominent innings score + Australian/English display | ✅ done |
| 7.5 Workspace-configurable match formats (enable/default/custom; history preserved) | ✅ done |
| 7.6 Historical team names & aliases (rename + source name; no auto-merge) | ✅ done |
| 7.1 Validation aggregation + Scorecard Approval workflow (draft/awaiting/approved/rejected) | ✅ done |
| 7.8 Automatic recalculation framework (approved-only, idempotent ledger) | ⏳ next |
| 7.9 Import integrity · 7.10 comprehensive tests · 7.11 manual acceptance | ⏳ outstanding |

**Known limitations / outstanding (Phase 7):**
- "Preserve last approved version" is flagged (`revised_since_approval`); the durable last-approved
  statistics preservation is implemented by the 7.8 recalculation ledger (next).
- Player-selector **club scoping** (backend ready: `list_people(organisation_id)` + MyClub
  affiliations) still needs the frontend wired — to be completed before final acceptance.
- Competition **points/ladders** architecture exists (`playing_conditions`); the user-friendly
  Points Manager + ladder calc is a later phase.
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
| **6** | **Matches & Scorecard Entry** | **🔄 In progress — Stage 7 under testing (NOT approved); Stage 8 not begun** |
| 7–18 | Validation → … → RMCC Trial | ⏳ Future |

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
