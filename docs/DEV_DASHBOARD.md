# OneStats — Development Dashboard

Lightweight, evidence-based status. Updated by hand from verified test/build runs — **no invented
completion percentages**. Full assessment: [43. Testing & Acceleration](43-testing-and-acceleration.md).

_Last updated: 2026-10-24 · branch `phase-2-foundation` · migration head `0025_affiliation_temporary`._

## Verified test evidence (last run)
| Suite | Result | Command |
|---|---|---|
| Backend (pytest) | **301 tests, passing** (DB tests roll back) | `run-tests.cmd backend` |
| Desktop (vitest) | **26 tests, passing** (incl. 2 jsdom interaction) | `run-tests.cmd desktop` |
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
