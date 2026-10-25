# Phase 13 — Records, Rankings & Achievements: Implementation Report

**Status: IMPLEMENTED — AWAITING COMBINED PHASE 11–13 MANUAL ACCEPTANCE.**
Not recorded as formally user-accepted. The combined acceptance programme is
[60](60-combined-acceptance-phase11-13.md). Phase 14 does not begin until the user accepts that programme.

Built **on top of** the Phase 12 statistics engine — no statistical formula is duplicated.

## Implemented functionality

- **13.1–13.4 Records engine** — all-time record holders composing the engine leaderboards (prominent
  No. 1 + expanded ranking + preserved ties + known-minimum flag), highest partnership, and
  season-by-season leaders (seasons never combined). Record categories cover batting, bowling, fielding,
  wicketkeeping, captaincy, partnerships, appearances and team records, filterable by the same scopes
  (incl. Home & Away / Finals / Grand Final).
- **13.5/13.14 Career & upcoming milestones** — workspace-configurable thresholds (RMCC defaults) with
  states confirmed / known-minimum / upcoming / indeterminate (unknown totals never confirm or deny a
  milestone); upcoming milestones computed from **confirmed** totals only.
- **13.6 Achievement badges** — distinguish automatically-calculated statistical achievements (with
  milestone state), administrator-confirmed honours, and historical/honorary recognition; a manual
  honour is never shown as a calculated record.
- **13.8 Life Members & honorary recognition** — explicitly recorded + authorised (`honour.manage`),
  with awarding organisation, date/season, evidence and optional linked photo; **never inferred** from
  statistics.
- **13.7/13.13 Records & Achievements UI** — a professional section (Club Management → Records &
  Achievements): all-time holders, seasonal leaders, upcoming milestones, Life Members, and one-click
  Club Record Book PDF.
- **13.16/13.17 Record reports + Club Record Book** — the one shared PDF framework (cover page, numbering,
  repeated headers); multi-section book (all-time records, seasonal leaders, Life Members) with honest
  known-minimum qualifications; never implies complete coverage.
- **13.12 Historical provenance / 13.15 recalculation** — records are approved-only and idempotent
  (reuse the Phase 7/12 recalc ledger), so corrections/merges/approvals update records without
  double-counting; known-minimums are flagged, confirmed totals distinguished.
- **API** — `/records` (all-time), `/records/seasonal`, `/records/milestones/{person}`,
  `/records/upcoming`, `/records/badges/{person}`, `/records/honours` (+ create/patch), `/records/book/pdf`.

## Player Profiles (added to Phase 13, 2026-10-26)

A complete professional **Player Profile** was audited and built on the existing one person identity,
the Phase 12 engine and Phase 13 records/honours/media — no second identity or engine.

- **Backend** `domain/records/player_profile.py`: career totals (all disciplines, merge-aware), season-
  by-season (not combined), match-by-match (missing figures null, never zero), clubs/teams, records held,
  milestones, badges, honours — in one `full-profile` call. Career scope is explicit.
- **Awards**: `honour.award_category` (migration 0051) enables custom award categories (Best & Fairest,
  Batting Award, Coach's Award, representative honours, …) alongside Life/Honorary Membership — recorded
  and authorised, never inferred.
- **Frontend** `/people/:personId`: professional header (avatar, role, Captain / Life Member / record-
  holder / premiership badges, clubs), adaptive career-summary cards (no misleading zero cards), and tabs
  for Overview, Batting, Bowling, Fielding & WK, Captaincy, Seasons, **Grand Finals**, Matches, Records &
  Milestones, Awards & Honours and Media (photo thumbnails). Known-minimum indicators throughout;
  light/dark; opened from the People directory.
- **Graphical career charts** (§15): the Seasons tab draws theme-aware, dependency-free SVG charts —
  runs per season, batting average by season, wickets per season and cumulative runs — with accessible
  (`role="img"` + descriptive label) text alternatives. Unknown values render as a gap, never as zero.
- **Dedicated Grand Finals section** (§21): a Grand Finals tab (and a matching PDF section) with grand
  finals played, **premierships** (grand finals the player's team won while featuring — a recorded
  result, never inferred), grand-final batting/bowling/captaincy figures and a list of every grand final.
  All figures come from the engine's `grand_final` classification split.
- **Profile PDF** (`reports/player_pdf.py`, `/people/{id}/profile.pdf`): a full career profile via the
  one shared framework (cover page, branding, career/season/records/milestones/awards) — same figures as
  on screen; private details excluded. A representative profile PDF was generated and provided for review.
- **Two real bugs were found and fixed**: (1) the engine's per-person aggregate grouped by `subject_id`,
  so a **merged** player's totals (contributions under more than one identity) were undercounted to a
  single identity — now it aggregates the whole merge-aware set; (2) `person_captaincy` always returned
  zeros because the empty-result guard tested a `matches` column the captaincy query does not select, so
  the profile's captaincy figures were silently blank — the guard now only short-circuits a genuinely
  empty result set.
- The combined acceptance programme ([60](60-combined-acceptance-phase11-13.md)) gains a **16-test Player
  Profiles section** (career charts + grand finals added; now 86 tests total; tests were added, not trimmed).

## Automated test results

Backend **≈543 passing, 2 skipped**; desktop **60 passing**; `tsc` + `ruff` clean. New Phase 13 suites:
milestones (confirmed/indeterminate/upcoming), records (holders/ties/seasonal leaders), honours + badges
(recorded-not-inferred; calculated vs awarded), Club Record Book PDF. **Phase 7–12 regression green.**

## Phase 11–13 regression summary

All three phases' automated suites pass alongside Phases 7–10: statistics engine + reconciliation +
partnerships + competition points + PDF, media archive + providers + migration + heritage + backup, and
records + milestones + badges + honours + record book. No critical defects outstanding.

## Known limitations & external dependencies

- **OneVault** (Phase 11) — no verified API; the adapter is capability-detected and reports unavailable
  (not operational). This is the **single** external dependency; it does not block any independently
  testable feature.
- The previously-noted Phase 12 follow-ups are now **complete and tested**: saved Report Builder
  configurations (§12.17, migration 0049), association-scale performance (§12.20, with a real
  conditional-join optimisation), multi-day first-innings + outright points (§12.12, migration 0050),
  and representative PDF generation + visual review (provided to the user).

## Professional report & PDF verification

The shared framework produces branded A4 portrait/landscape PDFs with logo, title, period, filters, date,
headers/footers, Page X of Y, repeated table headers, right-aligned numerics and wrapped long names;
on-screen and PDF figures come from the one engine and match. Vector tables, never screenshots.

## Phase 14 readiness

Records, milestones and achievements expose stable, permission-aware, deterministic interfaces with
supporting-source traceability — ready for Phase 14 (Ask OneStats) to consume. No Phase 14 work has begun.

**Do not begin Phase 14 until the user formally accepts the combined Phase 11–13 programme.**
