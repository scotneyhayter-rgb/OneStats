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
| 4. Statistical reconciliation | Numeric comparison on equivalent data+filters | Run-outs done (see below). Broader: TODO |
| 5. Correct critical defects | Fix verified calc/validation/integrity bugs + tests | **In progress** — run-out attribution fixed (commit f0b3bff) |
| 6. Recommendations | Prioritised roadmap (Deliverables F–J) | TODO |
| 7. Implement approved items | Only after user approves the programme | Not started (gated) |

## Deliverables (A–J) — tracking
- **A** Capability inventory — **CricketStatz done** (doc 01); OneStats catalogue+filters captured in doc 02 §0.
- **B** Filtering analysis — **done** (doc 01 §2 + doc 03 §2).
- **C** OneStats universal filtering proposal — **drafted** (doc 03), awaiting approval.
- **D** Report comparison — **drafted** (doc 02).
- **E** Statistical accuracy report — pending; run-out reconciliation complete.
- **F** Workflow/usability — pending.
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
  Next increments: multi-grade/season select, specific ground, innings/toss/batting-position; then a single
  reusable FilterBar + saved presets + chips across all surfaces.
- **P3 Reports:** data-quality report suite (High); milestones Achieved/Over-Time, hat-tricks, catches
  in-a-season/match/innings, winning-margin/run-chase (Medium).
- **P4 Analysis:** head-to-head, debut reports, On This Day, light analytics (Low–Medium).
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
