# OneStats — Audit Test Results

Evidence for the full system audit (2026-10-26). All live-DB tests run inside a transaction that is
rolled back; no data persists and no historical records are modified.

## Automated suites (after all audit fixes)

| Suite | Result |
|---|---|
| Backend (`pytest`) | **556 passed, 2 skipped** (≈113 s) |
| Desktop (`vitest`) | **62 passed** |
| Backend lint (`ruff onestats tests`) | **clean** |
| Desktop types (`tsc --noEmit`) | **clean** |
| Migrations | head `0051`; upgrade chain intact |

The 2 skips are environment-gated suites that need an external tool/credential, not failures.

## New tests added by the audit

### Independent statistics reference (`tests/test_audit_stats_reference.py`)
Expected values are hand-computed in the test, then checked against the engine (black-box) — not a
comparison of two engine outputs.

| Test | Verifies | Key hand-computed expectations |
|---|---|---|
| `test_batting_reference_values` | batting | avg 50/1=50.0; SR 50×100/40=125.0; one 50, one 100, one duck; **not-out → avg None**; **unknown runs → not a duck**, known-minimum, SR None |
| `test_bowling_reference_with_eight_ball_overs` | bowling | avg 24/5=4.8; SR 48/5=9.6; 5wi=1; **economy 4.0 at 8-ball overs, 3.0 at 6-ball** (proves configured over length) |
| `test_fielding_keeper_classification_reference` | fielding/keeping | keeper: 2 keeper catches + 1 stumping, keeper-dismissals 3, 0 field catches; slip: 1 field catch; cover: 1 run out, 0 catches |
| `test_captaincy_win_pct_reference` | captaincy | 4 captained, 2 W / 1 L / 1 NR → eligible 3, **win% 66.7** |

### Workspace isolation (`tests/test_isolation.py`)
- Added `test_stats_ledger_is_isolated_by_workspace`: a Phase 12 table
  (`match_stat_contribution`) is invisible across workspaces and rejects a write tagged for another
  workspace — a regression guard that newer tables carry FORCE RLS + policy, not only the Phase 3 tables.

### Database RLS coverage probe (`scratchpad/rls_audit.py`, run against the live schema)
- Every one of the **61** tables with a `workspace_id` column has `relrowsecurity = true`,
  `relforcerowsecurity = true` and ≥1 policy — **except `onboarding_draft`** (see BUG-005, by design).

## Verification of fixes

| Bug | How verified |
|---|---|
| BUG-001 | `test_bowling_reference_with_eight_ball_overs` + `test_recalc`/`test_import_integrity` still green after delegating to the engine |
| BUG-002 | `test_captaincy_win_pct_reference` (non-zero captaincy) + Player Profile render test |
| BUG-003 | PDF re-rendered to PNG (pymupdf) → now portrait, 2 pages |
| BUG-004 | PDF re-rendered → club name once; batting report title shown once |

## PDF visual inspection (rendered to images)

Generated through the real framework, rendered at 110 dpi and inspected:
- `01_batting_leaders` — landscape, branded header, zebra rows, right-aligned numerics, wrapped long
  names, "Page 1 of 4". ✔ (duplicate section heading removed by BUG-004 fix)
- `09_player_profile` — portrait cover + career summary, season table, records held, career milestones,
  awards & honours, qualification note, "Page 2 of 2". ✔ (was landscape before BUG-003)

Representative PDFs (9 reports incl. the player profile) are available in the session scratchpad and were
previously delivered for the user's visual review.

## Not covered by automated evidence (see remaining risks)

Live desktop click-through, association-scale performance under real load, the full malformed-import
matrix, interrupted-operation recovery, and a full backup→restore drill are part of the manual
acceptance programme and are **NOT TESTED** in this audit.
