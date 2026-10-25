# OneStats — Full System Audit (Phases 1–13)

**Pre-acceptance technical & functional audit.** Conducted 2026-10-26 as an independent review before
the combined Phase 11–13 manual acceptance programme. This audit actively looked for overlooked defects;
it did not simply re-run existing tests and declare health.

> This is a **technical quality review**, not user acceptance. Phases 11–13 remain
> **IMPLEMENTED — AWAITING COMBINED MANUAL ACCEPTANCE**. Phase 14 has not begun.

## 1. Executive summary

OneStats is in **good overall health** and materially more robust after this audit. The statistics
engine remains the single authoritative calculation source; after one fix it is now the *only* career
aggregation path. Workspace isolation is enforced at the database level across the whole schema (one
by-design exception, not a leak). Security fundamentals (Argon2id passwords, opaque tokens, bound-
parameter SQL, path-traversal guards, permission-gated endpoints) are sound. Professional PDFs were
rendered to images and visually inspected, and two presentation defects were fixed.

- **Defects discovered:** 5 (0 critical, 0 high, 3 medium, 2 low — one of the "low" is by-design).
- **Defects fixed & verified:** 4 (BUG-001…004). **Documented/by-design:** 1 (BUG-005).
- **Independent statistics verification:** 4 new reference tests (hand-computed expected values,
  including the eight-ball-over economy case) — all pass.
- **Automated suite after fixes:** backend **556 passed, 2 skipped**; desktop **62 passed**;
  `ruff` + `tsc` clean; migrations head `0051`, RLS verified on every workspace table.

No critical or high-severity defects are outstanding. The application is **ready to enter** the combined
Phase 11–13 manual acceptance programme, with the residual risks in `ONESTATS_REMAINING_RISKS.md`.

## 2. Methodology

Multi-pass, evidence-based. Passes actually performed in this audit:

| Pass | Area | How |
|---|---|---|
| 1 | Architecture & code review | Read the statistics core (`recalc`, `engine`, `partnerships`, `reconciliation`, `competition_points`, `records`), reports, profiles |
| 2 | Static analysis | Repo-wide scans for placeholders, bare excepts, f-string SQL, dead handlers, secret logging; `ruff` |
| 3 | Database & isolation | Live-schema RLS coverage probe (`rls_audit.py`) over every `workspace_id` table; migration head check |
| 6 | Statistics accuracy | **Independent** reference cases with hand-computed expected values (batting, bowling incl. 8-ball overs, fielding/keeping, captaincy) |
| 8 | Security | Password hashing, token handling, SQL-injection surface, path traversal, upload handling, endpoint authorisation |
| 11 | PDF & reporting | Generated representative PDFs and **rendered pages to images** for visual inspection |
| 12 | Regression | Full backend + desktop suites after every change |

Passes **not** exhaustively performed here (require the live app / scale / user judgement) are listed as
**NOT TESTED** or **PARTIAL** below and in `ONESTATS_REMAINING_RISKS.md`, per the rule that *PASS is never
substituted for NOT TESTED*. Several belong to the manual acceptance programme by design.

## 3. Module status

Legend: **PASS** tested & satisfactory · **FIXED** defect repaired & verified · **PARTIAL** some aspects
unverified here · **BLOCKED** external dependency · **NOT TESTED** not completed in this audit.

| # | Module | Status | Evidence / note |
|---|---|---|---|
| 1 | Windows Desktop App (shell/nav) | PARTIAL | Source scan clean (no dead handlers/TODOs/console logs); full click-through is manual acceptance |
| 2 | Backend API | PASS | Endpoints permission-gated; automated suite green |
| 3 | PostgreSQL database | PASS | RLS forced + policy on all 60+ workspace tables; migrations head 0051 |
| 4 | Workspaces & permissions | PASS | Isolation probe + isolation tests (now incl. stats ledger) |
| 5 | Clubs & associations | PASS (automated) | Domain suites green |
| 6 | Competitions & grades | PASS (automated) | Domain suites green |
| 7 | Teams & venues | PASS (automated) | Domain suites green |
| 8 | People & player management | PASS (automated) | Merge-aware aggregation re-verified |
| 9 | Matches & scorecards | PASS (automated) | Recalc idempotency/approval suites green |
| 10 | CricketStatz import | PARTIAL | Import-integrity suite green; broad malformed-file matrix is manual |
| 11 | Universal import framework | PARTIAL | Automated coverage green; interrupted/huge imports not load-tested here |
| 12 | AutoSync & online discovery | BLOCKED/PARTIAL | Connectors are documented-but-unimplemented (no verified access); correctly raise `NotImplementedError` |
| 13 | Historical Research Centre | PASS (automated) | Reconstruction/conflict suites green; evidence never overwrites approved stats |
| 14 | Media Archive | PASS | Path-traversal guarded, originals preserved + checksummed, per-workspace dirs |
| 15 | OneVault integration | BLOCKED | Capability-detected, reports unavailable; no verified API (by design) |
| 16 | Statistics engine | FIXED | BUG-001/002 fixed; single authoritative source; 4 independent reference tests pass |
| 17 | Reporting engine | PASS | On-screen/PDF parity test; filters/sorting covered |
| 18 | PDF export | FIXED | BUG-003/004 fixed; pages rendered & visually inspected |
| 19 | Competition points & ladders | PASS | Configured scheme honoured; first-innings + outright; unknown excluded |
| 20 | Records & rankings | PASS (OBS-1) | Ties preserved, known-minimum flagged; "best match bowling" shows wickets only (OBS-1) |
| 21 | Milestones & achievements | PASS (automated) | States confirmed/known-min/upcoming/indeterminate |
| 22 | Player profiles | FIXED | Captaincy fix (BUG-002); charts + Grand Finals added earlier; PDF portrait (BUG-003) |
| 23 | Awards & honours | PASS (automated) | Recorded/authorised, never inferred; custom categories |
| 24 | Dashboard | PARTIAL | Real-data queries reviewed; visual/role review is manual acceptance |
| 25 | Settings & configuration | PARTIAL | Not re-audited in depth this pass |
| 26 | Backup & recovery | PARTIAL | Manifest/checksum design reviewed; full restore drill is manual (Phase 11 test 18) |
| 27 | Audit logs & provenance | PASS (automated) | Writes audited; ledger traceable to source; approved-only |

## 4. Statistics accuracy (highest priority)

Verified against **independently hand-computed** expected values, not by comparing two engine outputs
(`tests/test_audit_stats_reference.py`):

- **Batting:** average = runs ÷ dismissals (not ÷ innings); strike rate over *recorded* balls only;
  50s/100s/ducks/HS; a **not out** yields no average; **unknown runs are never a duck** and flag a
  known-minimum. ✔
- **Bowling:** average = runs ÷ wickets; strike rate = balls ÷ wickets; **economy honours the configured
  over length** — proven with an eight-ball-over case (economy 4.0 at 8-ball, 3.0 at 6-ball); five-wicket
  innings and best-match wickets. ✔
- **Fielding / keeping:** keeper catches, caught-behind, stumpings, run outs and field catches are
  classified distinctly; run outs are never bowler wickets; total catches include keeper catches while
  keeper dismissals stay separate. ✔
- **Captaincy:** win % = wins ÷ eligible (no-results excluded) — e.g. 2 wins / 3 eligible = 66.7%. ✔

Data-integrity principles confirmed in code and tests: unknown ≠ zero; approved-only; last approved
version preserved until re-approval; merges combine without double counting; idempotent recompute;
historical over lengths respected.

## 5. Security

Argon2id password hashing; opaque high-entropy tokens; all runtime SQL uses bound parameters (f-string
SQL exists only in migrations over constant table-name lists); media/photo file access guards against
path traversal (`_safe_ref`/`_resolve`) with random stored filenames and preserved originals; endpoints
are permission-gated (onboarding is Super-Admin only). No secrets are logged. **Database-level workspace
isolation** is enforced on every workspace-scoped table (FORCE RLS + policy); the single exception is
`onboarding_draft` (BUG-005), which is by-design global Super-Admin state and not a tenant data path.

## 6. PDF & reporting

Representative PDFs were generated through the real shared framework and **rendered to images** for
inspection (not merely "generation succeeded"). Findings: landscape leaders table is correctly
proportioned with branding, zebra striping, right-aligned numerics, wrapped long names and "Page X of
Y"; two defects (profile forced landscape; cover/section duplication) were fixed and re-rendered to
confirm. On-screen/PDF parity is asserted by `test_reports_catalogue.py::test_pdf_matches_onscreen`.

## 7. What was fixed

BUG-001 (unify career stats to the one engine; drop hard-coded ×6 economy), BUG-002 (captaincy no longer
silently zero), BUG-003 (profile PDF portrait), BUG-004 (PDF duplication). See `ONESTATS_BUG_REGISTER.md`.

## 8. Readiness

**Ready for combined Phase 11–13 manual acceptance.** No critical/high defects outstanding. Residual
risks and the areas still to be exercised by hand are in `ONESTATS_REMAINING_RISKS.md`; test evidence is
in `ONESTATS_AUDIT_TEST_RESULTS.md`. **Phase 14 does not begin until the user formally accepts.**
