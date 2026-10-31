# Audit Deliverable D — Report Catalogue Comparison (CricketStatz ↔ OneStats)

**Stage 3.** Compares OneStats' **79-report catalogue** (`reports/catalogue.py`) against the **~230 CricketStatz
reports** captured in [01-cricketstatz-capability-inventory.md](01-cricketstatz-capability-inventory.md).
Not a count race — the goal is where OneStats is at parity, ahead, behind, or has an opportunity.

Classifications: **PARITY** · **ONESTATS BETTER** · **IMPROVEMENT REQUIRED** · **MISSING** · **DESIGN OPPORTUNITY** · **EXCLUDED** (user decision, e.g. Captain2).

## 0. Architectural parity (important)
Both apps already treat **scope (season/grade/competition/team/date/venue/finals) as a *filter*, not a separate
report**, over one engine. CricketStatz posts one form to every `mode`; OneStats' `CATALOGUE` reuses base types
(`batting`, `bowling`, `fielding`, …) with preset metric/sort. So CricketStatz's "…in a Season / …by Opposition /
…by Team" families are mostly **filtered views**, not 230 distinct statistics. This means OneStats closes most of
the apparent gap by **extending the filter bar** (Deliverable C), not by adding ~150 reports. **PARITY** on approach.

## 1. Category-by-category

| Area | CricketStatz | OneStats | Finding | Priority |
|---|---|---|---|---|
| Batting aggregates/averages/SR | Full (Top Runs, Avg, SR, by season/pos/opp) | Full (18 reports) | **PARITY**; OneStats adds honest qualification + known-minimum notes → **ONESTATS BETTER** on integrity | — |
| Milestones (bat/bowl/keep/catch): Upcoming / Achieved / Over-Time | Yes, 3 variants each | Only "Upcoming Milestones" (from badges) | **MISSING**: "Achieved" and "Over-Time" milestone reports | Medium |
| Centuries/fifties variants, ducks (golden/diamond/pairs), 90s/40s | Very rich (incl. Diamond Ducks, Duck Pairs, Century+Duck same match) | 90s, 40s, ducks, centuries, fifties, consec-no-duck | **MISSING** novelty cuts: golden/diamond ducks, duck pairs, century-and-duck, carrying the bat, consecutive hundreds/fifties | Low–Medium |
| Collapses (5–9 wicket batting collapses) | Yes | — | **MISSING** (team batting collapse reports) | Low |
| Bowling aggregates/avg/econ/SR/5WI/BBI | Full | Full (11 reports) incl. runs tie-break BBI | **PARITY** / **ONESTATS BETTER** (explicit over-length handling, runs tie-break) | — |
| Hat tricks | Yes (41) | — | **MISSING** | Medium |
| Over-level (most in an over: runs/sixes/balls/wides/wickets) | 6 reports | — | **MISSING** (needs ball-by-ball; export lacks it — see limitation) | Low |
| Fielding/keeping | Catches (field/keeper splits, by season/match/innings), stumpings, run-outs, dropped catches, dismissals | Catches (field/keeper split), stumpings, run-outs, keeper dismissals, WK-in-an-innings, fielder-bowler combos | **PARITY** on core; **MISSING**: catches-in-a-season/match/innings leaderboards, dropped catches, keeping milestones | Medium |
| Run-outs | Top Run Outs (per-fielder) | Most Run Outs | **IMPROVEMENT REQUIRED** → fixed this session (fielder backfill, commit f0b3bff). Now **PARITY** once a fresh export is applied | High (done) |
| Partnerships | Highest, by wicket, aggregates, century partnerships by pair | Highest, by wicket, aggregates, bowling groups (2/3/4) | **PARITY**; OneStats adds bowling-combination partnerships → **ONESTATS BETTER** | — |
| Captaincy | Wins, win%, consecutive toss, GF wins | 11 reports incl. by-season, comparison, GF, streaks | **ONESTATS BETTER** (richer captaincy suite, win% qualification) | — |
| Teams/results/ladders | Competition points (NRR/RpWr), margins, chases, streaks | Team records, win%, streaks, ladder (competition_points) | **PARITY** on core; **MISSING**: winning-margin reports, successful-run-chase, win-chance-by-1st-innings | Medium |
| Head-to-head / "by Opposition" | Pervasive (oppclub/oppteam filter + Match Summary by Opposition) | — (no opposition filter) | **MISSING / IMPROVEMENT REQUIRED** — the #1 gap; see Deliverable C | **High** |
| Appearances / longest serving / played-together / debuts | Full incl. youngest/oldest on debut, days between appearances | Appearances, longest-serving, matches-together, consecutive matches | **PARITY** on core; **MISSING**: debut reports (youngest/oldest/ducks-on-debut), age-based cuts | Low–Medium |
| "On This Day" (batting/bowling/partnerships) | Yes | — | **DESIGN OPPORTUNITY** (engagement feature) | Low |
| Data-quality / integrity linting | ~20 reports (fielder/bowler empty, captain/keeper missing, FOW mismatch, margin mismatch, listed twice, …) | 1 (reconciliation) + Research Centre gap checks | **MISSING / DESIGN OPPORTUNITY** — a proper data-quality report suite | **High** |
| Awards / honours | Team & individual awards by date | Awards & Honours, Life Members | **PARITY** | — |
| Umpires & scorers | Match lists, most matches | — | **MISSING** (low value for RMCC now) | Low |
| Batting Order Optimiser, Win Chance models | Yes | — | **DESIGN OPPORTUNITY** (analytics) | Low |

## 2. Where OneStats is already BETTER (keep and lead with these)
- **Honesty by construction**: unknown ≠ zero; known-minimum flags; strike/economy from recorded balls only;
  qualification thresholds stated on every average/rate report. CricketStatz shows raw numbers without this.
- **Reversible identity merges + provenance + audit** (Part 7) — CricketStatz has the data-quality reports but
  OneStats has the safe, reversible correction workflow and source attribution.
- **Captaincy & bowling-partnership depth** beyond CricketStatz.
- **Workspace isolation / RLS / approved-stats publishing** — a platform capability CricketStatz doesn't expose.

## 3. Genuinely missing, ranked for value (candidates for the roadmap — NOT yet built)
1. **Opposition filtering** across all reports + "Match Summary by Opposition" / head-to-head (High). Deliverable C.
2. **Data-quality report suite** (fielder/bowler/captain/keeper empty, FOW vs dismissals, margin vs totals) — High;
   leverages the integrity engine + Research Centre.
3. **Milestones: Achieved + Over-Time**; **Hat tricks**; **catches in a season/match/innings** (Medium).
4. **Winning-margin & successful-run-chase** reports; **debut** reports (Medium).
5. Novelty batting cuts (golden/diamond ducks, duck pairs, carrying the bat, consecutive 100s/50s) (Low–Medium).
6. **On This Day** + light analytics (Batting Order Optimiser, Win Chance) as engagement/Design Opportunities (Low).

## 4. Excluded / not applicable
- **Captain2** (second captain) — EXCLUDED by prior user decision.
- **Over-level reports** need ball-by-ball, which the CricketStatz export omits — NOT APPLICABLE until a
  ball-by-ball source exists (never fabricate).

## 5. Honesty note
No OneStats numbers were changed to match CricketStatz here beyond the verified run-out defect. Remaining items are
feature/coverage gaps, not calculation corrections. Numeric reconciliation of equivalent reports (Deliverable E)
is separate and proceeds against live CricketStatz figures, not assumptions.
