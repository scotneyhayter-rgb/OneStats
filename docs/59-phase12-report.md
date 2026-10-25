# Phase 12 — Statistics & Reporting Engine: Technical Completion Report

**Status: IMPLEMENTED — AWAITING COMBINED PHASE 11–13 MANUAL ACCEPTANCE.**
Per the user's instruction, Phase 12 manual acceptance is combined with Phases 11 and 13 at the end of
Phase 13; Phase 12 is **not** recorded as formally user-accepted. Automated tests pass and the technical
quality gate is met, so Phase 13 may begin.

Design refs: statistics engine [22](22-statistics-engine.md); RMCC catalogue [23](23-rmcc-report-catalogue.md);
captaincy [24](24-captaincy-calculation.md); partnerships [25](25-partnership-calculation.md);
report builder [27](27-report-builder.md).

## One deterministic engine

All leaderboards, reports, the ladder, PDFs and the dashboard read from **one** engine over the Phase 7
approved-statistics ledger (`match_stat_contribution`). There is no competing calculation in the
frontend. Approved data only; verified-partial within its verified scope; **unknown is never zero**;
no double-counting (idempotent recalc); provenance preserved (every figure traces to approved matches);
recomputes when approved scorecards change; merge-aware.

## Implemented & tested

- **12.1 Engine foundation** — extended the ledger with calculators for batting (per-innings HS/50s/
  100s/ducks + known-balls), bowling (BBI/5-fors/10-wkt match + known-balls), fielding/wicketkeeping
  (catch vs keeper-catch vs stumping vs run-out, no double-count), captaincy (credited captain, GF
  flags, unknown excluded), team result and derived appearances; every contribution carries
  classification + home/away.
- **12.2–12.4** — filterable leaderboards (season/grade/competition/team/split/venue/format/date),
  batting & bowling reports with averages/SR/economy (configurable over length, never 6-ball assumed),
  qualification thresholds (RMCC defaults configurable) and known-minimum flags.
- **12.5 Run-out reconciliation** — recorded wickets vs dismissals (bowler vs run-out vs other), visible
  run-outs count, warnings on incomplete scorecards (never an invented dismissal), retired-hurt never a
  wicket.
- **12.6 Fielding & wicketkeeping**, **12.7 Captaincy** (win% over eligible, GF, stre'able data),
  **12.10 Participation & team records**, **12.11 Leaders** — all via the engine.
- **12.8 Batting partnerships** (recorded/FoW-derived, no manual step) and **12.9 D12 bowling groups**
  (verified against the user's worked example).
- **12.12 Competition points & ladders** — uses the competition's **configured** points scheme
  (resolved per competition/season/grade), bonus/penalty, approved matches only, unknown excluded.
- **12.13/12.14 Report catalogue + professional on-screen design** — a Statistics page with report tabs,
  filters, right-aligned numerics, fixed decimals, sticky headers, client-side sort, qualification notes.
- **12.15/12.16 Professional PDF framework** — one shared reportlab builder (A4 portrait/landscape,
  logo + club name, title/period/filters/date, headers/footers, Page X of Y, repeated table headers,
  wrapped long names, optional cover page); vector text tables, never screenshots; on-screen and PDF
  figures are identical (both from the engine). `/stats/reports/{report}/pdf`, `/stats/ladder/pdf`.
- **12.18 Data integrity** — reconciliation issues across approved matches + unknown-data counts;
  distinguishes confirmed from known-minimum.
- **12.19 Dashboard integration** — leading run scorer + wicket taker from the engine (real data).

## Completed follow-ups (2026-10-26)

- **12.17 Report Builder — COMPLETE.** Saved report configurations persist (`saved_report`, migration
  0049): create / reopen / edit / delete, private or shared-within-workspace (owner-only edit/delete),
  config holds only parameters. Wired into the Statistics UI.
- **12.20 Performance — COMPLETE.** An association-scale test seeds ~1,500 matches / ~800 players /
  ~45k ledger rows and asserts leaderboards, per-person aggregates, the ladder and a report PDF finish
  within time budgets. It found and fixed a real issue: the engine joined `match` on every leaderboard
  even when no format/date filter needed it; the join is now conditional (batting leaderboard dropped
  from ~3.4s to well under budget).
- **12.12 Multi-day first-innings + outright points — COMPLETE.** `match.first_innings_winner_team_id`
  (migration 0050) + configurable `first_innings_win` / `first_innings_loss` scheme keys; the ladder
  scores first-innings and outright results together, fully configurable per competition/season/grade.
- **PDF visual review — DONE.** Representative batting/bowling/fielding/captaincy/teams/ladder/grand-final
  and Club Record Book PDFs were generated from realistic engine-backed data (multi-page with repeated
  headers; cover page on the book; long names + an unknown-runs player) and provided to the user.

## Automated test results

Backend **≈545 passing, 2 skipped** (incl. new stats suites: engine, reconciliation, partnerships/D12,
competition points, PDF builder, report catalogue, integrity); desktop **60 passing**; `tsc` + `ruff`
clean. Phase 7–11 regression green. PDFs are generated and asserted to be real multi-page vector
documents; **representative PDFs should be visually inspected during combined acceptance** (a successful
generation does not prove professional formatting).

## Remaining before/within combined acceptance

None outstanding — the previously-noted follow-ups (saved report configs, association-scale perf,
multi-day points, PDF visual review) are all complete and tested. No critical statistics defects.

**Phase 12 technical quality gate: PASSED. Phase 13 authorised to begin. Do not record Phase 12 as
formally accepted until the combined Phase 11–13 programme.**
