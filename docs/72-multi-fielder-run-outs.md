# 72. Multi-Fielder Run-Outs (residual risk R-3)

**Implemented 2026-10-26.** Resolves R-3 ([ONESTATS_REMAINING_RISKS.md](ONESTATS_REMAINING_RISKS.md)): a
run-out often involves more than one fielder (e.g. a thrower plus whoever breaks the stumps), but only one
fielder could be credited.

> No phase is marked user-accepted; automated tests are development assurance.

## Data-model decision

- The **primary** run-out fielder stays on `batting_entry.fielder_person_id` and is credited exactly as
  before (`run_outs`) — so **no existing figure changes**.
- A new `dismissal_fielder` table records each **additional** involved fielder for a dismissal, with a role
  (`assist` default, or `thrower`/`keeper`/`fielder`/`other`). Workspace-isolated (FORCE RLS); unique per
  (dismissal, person); cascade-deleted with the entry.
- The one deterministic engine credits each additional fielder a distinct **`run_out_assists`** — a
  separate, non-overlapping metric. For display it also exposes **`run_out_involvements = run_outs +
  run_out_assists`**. The dismissal is still **one wicket** (reconciliation unchanged); nothing is
  double-counted and no involvement is invented.

Assisting fielders are only valid for a run-out with a primary fielder; changing the dismissal away from
run-out (or clearing the primary fielder) removes them automatically. The primary fielder and duplicates are
never accepted as assists.

## How it is used

- **Scorecard**: in the batting grid's **Fielder** cell, a run-out shows an "**+ add fielder**" control to
  record the other involved fielders (chips with remove); saving re-runs the engine for the innings.
- **API**: `GET` / `PUT /workspaces/{id}/innings/{iid}/batting/{entry}/run-out-fielders`
  (gated `match.manage`).
- **Stats**: `fielding_leaders` and `person_fielding` (and the player profile) now return `run_out_assists`
  and `run_out_involvements` alongside `run_outs`.

## Code map

- `db/migrations/versions/0057_dismissal_fielder.py` — the RLS-isolated table.
- `domain/batting.py` — `set_run_out_fielders`, `list_dismissal_fielders`; clears on non-run-out update.
- `domain/recalc.py::_calc_player_fielding` — credits `run_out_assists` from `dismissal_fielder`.
- `domain/stats/engine.py` — exposes `run_out_assists` / `run_out_involvements`.
- `api/v1/batting.py` — the two endpoints.
- `apps/desktop/src/features/scorecard/grids.tsx` (`RunOutAssists`), `lib/api.ts`.

## Automated coverage

- `tests/test_stats_engine.py::test_multi_fielder_run_out_credits_assist_without_changing_primary` — assist
  credited, primary unchanged, involvements combine, catch retained, reconciliation still one run-out;
  assists cleared when the dismissal changes.
- `tests/test_stats_engine.py::test_set_run_out_fielders_rejects_non_run_out_and_primary` — guards.

Backend regression after this work: **637 passed, 2 skipped**. Frontend 74 passed; typecheck clean.

## Scope note

R-2 (full "Best Bowling in a Match" figure with runs tie-break) was already implemented
(`best_bowling_in_match` ranks by wickets then fewest runs). R-4 (career economy across mixed over-lengths)
remains a documented approximation — per-season/era figures are exact. R-1 (onboarding draft scoping) was
resolved earlier.
