# OneStats ↔ CricketStatz Audit — Roadmap & Status

Master prompt: a comprehensive comparison of OneStats against CricketStatz (the trusted numeric benchmark),
to make OneStats a *superior* platform — not a clone. Staged, with implementation of substantial features
gated on the user's approval. Verified statistical bug fixes may proceed immediately where safe.

## Guardrails (from the prompt)
- CricketStatz is the numeric reference, not a product to copy. No proprietary code/graphics/layout.
- Only authorised, read-only access and permitted exports. Never alter the CricketStatz database.
- Never invent statistics; unknown ≠ zero. Preserve approved historical records, RLS/workspace isolation,
  and the agreed forfeit/captaincy/partnership rules. Keep the 79-report catalogue unless change is justified.
- Exclude CricketStatz Captain2 (prior decision). Don't rebuild the Windows installer during this exercise.
- Don't claim internal tests prove CricketStatz parity.

## Stages & status

| Stage | Scope | Status |
|---|---|---|
| 1. Discovery | Inventory CricketStatz + OneStats capabilities | **Done** — CricketStatz → [01](01-cricketstatz-capability-inventory.md); OneStats catalogue (79) + engine filters captured in [02](02-report-comparison.md) |
| 2. Filtering analysis | CricketStatz filter model; design OneStats universal filter | **Done (proposal)** → [03-universal-filter-proposal.md](03-universal-filter-proposal.md) (Deliverable C), awaiting approval |
| 3. Report analysis | Report-by-report CricketStatz vs OneStats | **Done** → [02-report-comparison.md](02-report-comparison.md) (Deliverable D) |
| 4. Statistical reconciliation | Numeric comparison on equivalent data+filters | **Done (batting+bowling)** → [04-statistical-reconciliation.md](04-statistical-reconciliation.md): 19 comparisons, 17 exact parity, 2 stale-source, **0 calc defects**. Fielding = known source staleness. |
| 5. Correct critical defects | Fix verified calc/validation/integrity bugs + tests | **In progress** — run-out attribution fixed (commit f0b3bff) |
| 6. Recommendations | Prioritised roadmap (Deliverables F–J) | TODO |
| 7. Implement approved items | Only after user approves the programme | Not started (gated) |

## Deliverables (A–J) — tracking
- **A** Capability inventory — **CricketStatz done** (doc 01); OneStats catalogue+filters captured in doc 02 §0.
- **B** Filtering analysis — **done** (doc 01 §2 + doc 03 §2).
- **C** OneStats universal filtering proposal — **drafted** (doc 03), awaiting approval.
- **D** Report comparison — **drafted** (doc 02).
- **E** Statistical accuracy report — **done** (doc 04): batting+bowling benchmark-verified against live
  CricketStatz, 0 calc defects; only stale-source diffs remain (closed by re-import + fielder backfill).
- **F** Workflow/usability — **done** (doc 05) + **scorecard-entry deep-dive** (doc 06): OneStats faster for
  everyday tasks and the stronger/safer *post-match* editor (inline advisories, inline player creation,
  auto-partnerships, multi-fielder run-outs, draft→approved). CricketStatz's one real entry advantage is
  **live ball-by-ball scoring** (OneStats gap). Quick wins: margin auto-calc, official-total override,
  per-match data-quality check.
- **G** Recommended new capabilities — seeded in doc 01 §4 + doc 02 §3.
- **H** Prioritised roadmap — see §"Prioritised recommendations" below (growing).
- **I** Implementation readiness — pending.
- **J** Executive summary — pending (final).

## Prioritised recommendations so far (Deliverable H, growing)
- **P1 Correctness:** run-out fielder attribution — **fixed** (f0b3bff); broader numeric reconciliation (E) next.
- **P2 Universal filtering:** **opposition filtering — SHIPPED** (b9120fa) and **user-adjustable min-innings
  qualification — SHIPPED** (401b61c; batting+bowling, filtered-population, excludes small samples from rate
  rankings). The **acceptance test now fully holds**: RMCC · date range · A Grade · vs Pomonal · home-and-away ·
  min 10 innings · sorted by average are all expressible on the Statistics screen (tests
  `test_opposition_filter_scopes_stats_to_the_chosen_opponent`, `test_min_innings_qualification_flags_small_sample_batters`).
  **Specific-ground filter + active-filter chips — SHIPPED** (85d25a4; venue_id via match join; the Statistics
  screen now shows every active filter as a removable chip with Clear all, per Part 3.5). Next increments:
  multi-grade/multi-season select, innings/toss/batting-position; then extract one reusable FilterBar (with the
  chips) + saved presets, and reuse it on player/team profiles, dashboards and Ask OneStats.
- **P3 Reports:** **data-quality report suite — SHIPPED** (534df4c; a `data_quality` module of scorer-error
  checks — missing fielder/bowler, bowler-is-fielder, captain/keeper missing, duplicate batter/bowler, empty
  innings — surfaced as a Research Centre "Data Quality" tab with per-match drill-down; validated live, e.g.
  1,037 missing fielders, 0 duplicates). Remaining: milestones Achieved/Over-Time, hat-tricks, catches
  in-a-season/match/innings, winning-margin/run-chase (Medium).
- **P4 Analysis & UX:** **Player Compare — SHIPPED** (e6a7fda; 2–6 players side-by-side across batting/
  bowling/fielding/captaincy under shared filters incl. opposition, best-value highlight + CSV; neither app
  had it). **Season-vs-season compare — SHIPPED** (d622b7a; a "Compare seasons" mode on Player Compare:
  one player across seasons). Remaining: grade-without-competition, report search/favourites; plus
  **head-to-head — SHIPPED** (feed4af; club-vs-club record + win bar + match list, reuses the
  opposition filter). Remaining: debut reports, On This Day, light analytics (Low–Medium). From Deliverable F.
- **Scorecard entry (doc 06):** **per-match data-quality check — SHIPPED** (cca5aea; a "Check this scorecard"
  button in the editor, scoped `data_quality` scan). Found that **official-total override and automatic
  result/margin already exist** (OneStats auto-calculates margin; CricketStatz needs a manual Calc) — no work
  needed. Remaining: **live ball-by-ball scoring** (Large — the one CricketStatz entry capability OneStats
  lacks; scope separately) and per-batter dot balls (minor).
- All P2+ items are Stage-7 work — **built only after you approve this direction.**

## Confirmed defects fixed (Stage 5)
1. **Run-out fielder attribution undercounted.** OneStats faithfully reproduced a *stale* CricketStatz export
   that omitted fielders the scorer added later (Hayter 13 vs 18; Robinson R 0 vs 2, etc.). Fix: a fielder
   backfill that copies newly-known fielders from a fresher re-import onto existing matches and recomputes,
   without overwriting manual corrections. Commit **f0b3bff**; regression test
   `test_backfill_fills_fielders_added_to_source_after_original_export`. Full analysis in the session notes.

## How this proceeds
Each future turn advances one or more stages and updates this file. Nothing in Stage 7 (major UI/feature
work such as the universal filter bar or new reports) is built until the Stage 6 roadmap is approved.
