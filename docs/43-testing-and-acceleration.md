# 43. Testing Capability, Workstreams & Accelerated Roadmap

**Deliverable 43.** Assessment and plan requested during Phase 6 Stage 7. Evidence-based; no
completion percentages are invented. This document changes no application behaviour.

## 43.1 Current testing capability (assessed)
| Capability | State |
|---|---|
| **Backend unit/service/API tests** | **301 pytest tests** in `services/api/tests/` (~40 files). Each test runs in a transaction that is **rolled back** (no data persists); DB-backed tests **skip** when no DB credential is configured. API tests use FastAPI `TestClient`. |
| **Database test facility** | Transactional rollback per test against the live dev PostgreSQL, exercising **FORCE row-level security** as the least-privilege `onestats_app` role. No separate test DB needed; nothing is reset. |
| **Frontend logic tests** | **vitest** (node env) — navigation, permissions, scorecard logic. |
| **Frontend interaction tests** | **NEW this stage:** jsdom + `@testing-library/react` + `user-event` (dev-only). `grids.interaction.test.tsx` drives the player dropdown (open → search → select → field populates). Opt-in per file via `// @vitest-environment jsdom`. |
| **Desktop total** | **26 vitest tests** across 4 files. |
| **Build scripts** | `apps/desktop`: `npm run build` (tsc + vite), `test`, `tauri`. Backend: `alembic`, `pytest`, `ruff`. No root orchestration previously — **added `run-tests.cmd`** (below). |
| **End-to-end / native Tauri** | **None.** There is no automated test that drives the real Tauri window. Browser/jsdom tests verify React behaviour and the web bundle, **not** native Tauri (window chrome, OS icon, webview packaging). Those remain **manual**. |
| **CI** | **None** (`.github/workflows` absent). See §43.6 decision D-ACC-1. |
| **Git branches** | `main` (base) and `phase-2-foundation` (active). |
| **Synthetic test data** | **NEW:** `services/api/scripts/seed_testdata.py` (see §43.3). |

**Honest limits:** jsdom interaction tests are real UI-event tests but run in a simulated DOM, not
Chromium and not Tauri. They do **not** verify native Tauri functionality or rendering.

## 43.2 Testing infrastructure added (minimum practical)
1. **jsdom + testing-library** for real React interaction tests (committed `9784ec9`).
2. **`run-tests.cmd`** (repo root) — one Windows command for both suites. A `.cmd` is **not** blocked
   by PowerShell's execution policy (unlike `.ps1`).
3. **`scripts/seed_testdata.py`** — repeatable synthetic data in an isolated workspace.

### Windows commands
```bat
run-tests.cmd            REM backend (pytest) + desktop (vitest)
run-tests.cmd backend    REM backend only
run-tests.cmd desktop    REM desktop only
```
Or individually:
```bat
cd services\api && .venv\Scripts\python -m pytest -q
cd apps\desktop && node_modules\.bin\vitest run
cd apps\desktop && npm run build        REM tsc + vite type-check/build
```

### Priority coverage (TASK 2) — current state
| Priority | Covered by | State |
|---|---|---|
| 1. Dropdown selection & persistence | `grids.interaction.test.tsx` (select→field) + backend persistence tests (`test_batting` etc.) | ✅ |
| 2. Player Wizard / fill-in participation | `test_participation.py` (Bill Smith, team_season_players) | ✅ backend; ⏳ UI |
| 3. Batting row removal & reordering | — | ❌ not yet (feature not built) |
| 4. Batting/bowling calculations | `test_batting`, `test_bowling`, `test_innings` | ✅ backend |
| 5. FOW & automatic partnerships | `test_partnerships` (FOW/manual) | ✅ FOW/manual; ❌ auto-derivation not built |
| 6. Save & reopen | backend persistence tests; Phase-1 verify script | ✅ service-level |
| 7. Permissions & isolation | `test_isolation`, `test_permissions`, per-feature isolation tests | ✅ |
| 8. Duplicate player/match prevention | `test_person_resolution`, batting/bowling duplicate guards | ✅ |

## 43.3 Synthetic test data (TASK 4)
`services/api/scripts/seed_testdata.py` creates ONE workspace named **`ONESTATS SYNTHETIC TEST`**
and only ever touches a workspace of that name — it **never** resets the DB or alters real/other
workspaces. It seeds: two clubs & teams, a competition/grade, **two seasons**, registered players +
a **fill-in** (Bill Smith, registered Sandbox, filling in for Test Valley), a **complete** scorecard
(batting, bowling, FOW, partnerships) with a **retirement** and a **deliberate known inconsistency**
(official total set below the card), and an **incomplete** historical match.
```bat
cd services\api
.venv\Scripts\python scripts\seed_testdata.py            REM create (idempotent)
.venv\Scripts\python scripts\seed_testdata.py --teardown REM remove only the synthetic workspace
```

## 43.4 Parallel development workstreams (TASK 3)
Classified against the 18-phase roadmap and current dependencies:

**A — Independent, safe to parallelise now** (different files/areas, additive):
- Scorecard UI features on the built foundation: **batting-order management** (remove/reorder),
  **Player Wizard UI**, **auto-calc display** (strike rate/economy/run rate) — each touches distinct
  components; coordinate only on `ScorecardEditor.tsx`/`grids.tsx`.
- **Documentation** phases (research-centre spec, report catalogue) — pure docs.

**B — Requires completed DB/API foundations** (do after their backend lands):
- **Automatic partnerships from FOW** (needs a small migration + domain, then UI).
- **Validation categories** (Error/Warning/Incomplete/Verified) — extends existing validation.
- Phase 12 statistics engine — needs the participation foundation (now in place).

**C — Requires integration testing before merge:**
- Anything spanning backend + desktop in one flow (Player Wizard end-to-end, partnership recompute).

**D — Requires manual approval before proceeding:**
- **Phase 6 Stage 8** (CricketStatz import) and every later phase.
- Any schema change to completed-stage tables.

### Git strategy (to prevent sessions overwriting each other)
- Keep `main` as the integration base; **one short-lived branch per workstream** off `main`
  (e.g. `stage7/partnerships`, `stage7/player-wizard`, `stage7/batting-order`).
- For concurrent sessions, use **git worktrees** so each has its own working directory on its own
  branch: `git worktree add ../OneStats-partnerships stage7/partnerships`. This avoids two sessions
  editing the same checkout. Merge to `main` only after `run-tests.cmd` is green.
- Rule: a workstream touching a shared file (`ScorecardEditor.tsx`, `grids.tsx`, `lib/api.ts`,
  `matches.py`) is **serialised**, not parallelised, to avoid conflicts. **Do not launch parallel
  sessions automatically** — propose them for approval.

## 43.5 Accelerated roadmap (TASK 6)
**First usable desktop release (internal alpha)** — the smallest set that lets RMCC enter and read
real scorecards reliably:
1. Finish **Stage 7**: batting-order management, Player Wizard UI, automatic partnerships,
   validation categories, auto-calc display. *(Backend foundations for participation are done.)*
2. **Stage 8**: CricketStatz import (bulk-load existing history) — **needs approval**.
3. Minimal **Phase 12** read-only aggregates for a basic player/club stats view.
→ This yields a usable Windows app for data entry + import + basic stats, well before the full
18-phase product (which adds discovery, research centre, media, full reporting, Ask, publishing,
mobile, release hardening, trial).

**Sequence & parallelism:** within Stage 7, run the three UI features (batting-order, wizard,
auto-calc) as separate branches (A); do auto-partnerships backend first (B) then its UI; add
validation categories last (touches several validators). **Testing checkpoints:** `run-tests.cmd`
green before each merge; a manual scorecard walkthrough on the synthetic workspace before declaring
a feature ready.

**Main technical risks:** (1) shared-file contention in the scorecard editor → serialise; (2)
attribution correctness under edits/recompute → covered by participation tests, extend on each
change; (3) Tauri-only issues invisible to jsdom → keep a manual Tauri checklist; (4) stale Vite
dep cache after import changes → `rm -rf node_modules/.vite` + restart.

**Greatest time savings:** the DB rollback test harness (no fixtures/teardown), the synthetic seed
(instant realistic state), and `run-tests.cmd` (one-command regression) — plus serial, small,
tested branches instead of large rewrites.

## 43.6 Decisions requiring your approval
- **D-ACC-1 — Add CI?** A GitHub Actions workflow running `pytest` + `vitest` on push would catch
  regressions automatically. Needs a CI Postgres (or the DB tests skip there). Approve adding it?
- **D-ACC-2 — Which Stage 7 feature next** (batting-order mgmt / Player Wizard UI / automatic
  partnerships)? These can be branches; say the order.
- **D-ACC-3 — Stage 8 (CricketStatz import)** remains gated — not started without approval.
- **D-ACC-4 — Parallel sessions / worktrees:** approve the branch-per-workstream + worktree model
  before any parallel session is launched (none launched automatically).
