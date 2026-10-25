# OneStats — RMCC Requirements-to-Implementation Matrix

Reconciles every report in the original specifications — [22-statistics-engine.md](22-statistics-engine.md),
[23-rmcc-report-catalogue.md](23-rmcc-report-catalogue.md), [24-captaincy-calculation.md](24-captaincy-calculation.md),
[25-partnership-calculation.md](25-partnership-calculation.md), [27-report-builder.md](27-report-builder.md) —
against what is implemented in the Report Catalogue (Phase 12 expansion). Produced 2026-10-26.

**Status key:** **✅ Implemented & tested** (automated coverage) · **🟢 Implemented** (opens & exports;
covered by the "every entry opens" loop test, no dedicated reference assertion) · **🟡 Partial**
(available but with a documented limitation or via a filter rather than a dedicated breakdown) ·
**🔴 Outstanding** (not yet implemented — scheduled).

All reports use the ONE deterministic engine (deliverable 22). Scope — season, grade, competition, team,
date, format, venue, and the Home&Away / Finals / Grand Final split (§23.10) — is a **filter**, never a
separate report. RMCC qualification thresholds (§21) are applied only to the averages/rates/% reports and
are configurable. The catalogue holds **79** distinct reports; CSV + PDF export on tabular reports.

**Update 2026-10-26:** all six previously-outstanding reports are now implemented and tested, the
best-bowling-in-a-match runs tie-break is corrected, the **approved forfeit policy** is applied
throughout, and **Cricket Statz "Captain2" is EXCLUDED BY USER DECISION — NOT REQUIRED** (not an open
item).

## §23.1 Player careers

| Report | Format | Calc | Status | Catalogue id |
|---|---|---|---|---|
| Most Matches | Top list | distinct matches played | 🟢 | `part_most_matches` |
| Most Consecutive Matches | Top list | longest run over the team's played-fixture sequence | ✅ | `part_consec_matches` |
| Most Wins | Top list | matches played, team won | 🟢 | `part_most_wins` |
| Longest Serving | Top list | span first→last appearance; seasons & years | 🟢 | `part_longest_serving` |
| Most Matches Played Together | Pair list | matches both played (unordered pair) | ✅ | `part_matches_together` |

## §23.2 Team streaks

| Report | Calc | Status | Catalogue id |
|---|---|---|---|
| Most Consecutive Wins | longest win run (chronological) | ✅ | `team_consec_wins` |
| Most Consecutive Losses | longest loss run | 🟢 | `team_consec_losses` |
| Most Consecutive Without a Loss | unbeaten run | 🟢 | `team_unbeaten` |
| Most Consecutive Without a Win | winless run | 🟢 | `team_winless` |

Outcome handling per §23.2: no-results/abandoned skipped; **unknown breaks the known sequence and flags a
known-minimum**; never assumed win/loss. Missing historical *fixtures* can't be detected from recorded
matches, so streaks are over recorded approved matches and flagged known-minimum when the sequence has
unknowns or undated matches.

## §23.3 Batting

| Report | Format | Status | Catalogue id |
|---|---|---|---|
| Top Run Aggregates | Top list | 🟢 | `bat_most_runs` |
| Most Runs in a Season | All-time list of (player, season) | ✅ | `bat_most_runs_season` |
| Top Run Scores | Individual innings list (No.1 + list) | ✅ | `bat_top_scores` |
| Most Runs in a Match | Individual match list | 🟢 | `bat_most_runs_match` |
| Top Batting Averages (min 500) | Top list, qualified | 🟢 | `bat_highest_average` |
| Most Boundaries | Top list | ✅ | `bat_most_boundaries` |
| Most Sixes | Top list | 🟢 | `bat_most_sixes` |
| Most Fours | Top list | 🟢 | `bat_most_fours` |
| Most 90s | Top list | ✅ | `bat_most_90s` |
| Most 40s | Top list | ✅ | `bat_most_40s` |
| Most Centuries | Top list | 🟢 | `bat_most_centuries` |
| Most Half-Centuries | Top list | 🟢 | `bat_most_fifties` |
| Top Batting Strike Rates (min 100) | Top list, qualified | 🟢 | `bat_best_strike_rate` |
| Most Ducks | Top list | 🟢 | `bat_most_ducks` |
| Most Consecutive Scores Without a Duck | Top list | ✅ | `bat_consec_no_duck` |

## §23.4 Batting partnerships

| Report | Status | Catalogue id |
|---|---|---|
| Top Partnerships by Wicket | 🟢 | `part_by_wicket` |
| Top Partnerships | 🟢 | `part_highest` |
| Top Partnership Aggregates (pair) | 🟢 | `part_aggregates` |

## §23.5 Bowling partnerships (D12)

| Report | Status | Catalogue id |
|---|---|---|
| 2-player combinations | 🟢 | `bowl_pairs` |
| 3-player combinations | 🟢 | `bowl_trios` |
| 4-player combinations | 🟢 | `bowl_quartets` |

## §23.6 Bowling

| Report | Status | Catalogue id | Note |
|---|---|---|---|
| Top Wicket Takers | 🟢 | `bowl_most_wickets` | |
| Top Bowling Averages (min 50) | 🟢 | `bowl_best_average` | |
| Most Wickets in a Season | 🟢 | `bowl_most_wickets_season` | |
| Best Bowling in a Match | ✅ | `bowl_best_match` | most wickets, then fewest runs (runs tie-break); ties preserved |
| Top Economy Rates (min 50) | 🟢 | `bowl_best_economy` | configured over length |
| Top Bowling Strike Rates (min 50) | 🟢 | `bowl_best_strike_rate` | |
| Most Expensive Bowling in an Innings | ✅ | `bowl_most_expensive` | |
| Most 5-Wicket Innings | 🟢 | `bowl_most_five_fors` | |
| Most Ducks Inflicted | ✅ | `bowl_most_ducks_inflicted` | |

## §23.7 Fielding & wicketkeeping

| Report | Status | Catalogue id |
|---|---|---|
| Top Fielder–Bowler Combinations | ✅ | `field_bowler_combos` |
| Top Catches (fielding, excl. keeping) | 🟢 | `field_most_outfield` |
| Top Wicketkeeper Catches | 🟢 | `wk_most_catches` |
| Top Wicketkeeper Stumpings | 🟢 | `wk_most_stumpings` |
| Top Wicketkeeper Dismissals (total) | 🟢 | `wk_most_dismissals` |
| Top Wicketkeeping in an Innings | ✅ | `wk_best_innings` |
| Combined Catches (field + keeper) | 🟢 | `field_most_catches` |
| Top Run Outs | 🟢 | `field_most_run_outs` |

## §23.8 / 24.3 Captaincy

Uses **actual match captaincy records** (acting captain if recorded, else captain); never infers that the
season captain led every match; no match double-credited (§24.1).

| Report | Status | Catalogue id | Note |
|---|---|---|---|
| Most Matches Captained | ✅ | `capt_most_matches` | W/L/D/T/NR columns included |
| Most Wins as Captain | 🟢 | `capt_most_wins` | |
| Best Winning % (min 20, configurable) | 🟢 | `capt_best_win_pct` | wins ÷ eligible (NR excluded) |
| Most Grand Finals Captained | 🟢 | `capt_most_gf` | |
| Most Grand Final Wins as Captain | 🟢 | `capt_most_gf_wins` | |
| Most Consecutive Wins as Captain | ✅ | `capt_consec_wins` | |
| Captaincy Unbeaten Streak | 🟢 | `capt_unbeaten` | |
| Captaincy Winless Streak | 🟢 | `capt_winless` | |
| Win/Loss/Draw/Tie Record | 🟢 | `capt_most_matches` | the W/L/D/T columns |
| Captaincy by Season | ✅ | `capt_by_season` | dedicated per-season × captain breakdown (results, win %, finals, GF, premierships) |
| Captaincy by Club / Competition / Grade | 🟢 | `capt_most_matches` + scope filters | |
| Most Consecutive Matches Captained | ✅ | `capt_consec_matches` | over the team's played fixtures; no-play forfeits skipped |
| Complete Individual Captaincy Record | 🟢 | Player Profile → Captaincy | per-player breakdown on the profile |
| Captaincy Comparison Reports | ✅ | `capt_compare` | side-by-side tool at `/statistics/captaincy-compare` |

## §23.9 Other records

| Report | Status | Catalogue id |
|---|---|---|
| Annual leading run scorers | 🟢 | `seasonal_leaders` |
| Annual leading wicket takers | 🟢 | `seasonal_leaders` |
| Best single-season run totals | 🟢 | `rec_best_season_runs` |
| Best single-season wicket totals | 🟢 | `rec_best_season_wkts` |
| Highest innings & match performances | ✅ | `bat_top_scores`, `rec_highest_scores`, `bat_most_runs_match` |
| Highest partnerships by wicket | 🟢 | `part_by_wicket` |
| Grand Final records | 🟢 | `gf_batting`, `gf_bowling`, + the split on every match report |
| Player milestones | 🟢 | `milestones_upcoming` (+ profile) |
| Career achievements | 🟢 | `honours_all` (+ profile badges) |

## Report-format distinctions (preserved, per the mandatory addition)

- **All-Time Top-10 / leaderboards** — the ranked lists (e.g. `bat_most_runs`), No.1 prominent, full ranking below.
- **Annual No.1 leaders** — `seasonal_leaders` (one leader per season; seasons never combined).
- **Individual No.1 match / innings records** — `bat_top_scores`, `bat_most_runs_match`, `bowl_most_expensive`
  (the single best performance is the No.1 of the list; not forced into a fixed Top-10 shape).
- **Partnership records** — `part_highest`, `part_by_wicket`, `part_aggregates`, bowling combinations.

## Completed 2026-10-26 (previously outstanding)

All six items the earlier matrix flagged are now **implemented and tested**:

1. **Most Consecutive Matches** (player) — `part_consec_matches`. ✅
2. **Most Consecutive Matches Captained** — `capt_consec_matches`. ✅
3. **Most Consecutive Scores Without a Duck** — `bat_consec_no_duck`. ✅
4. **Top Wicketkeeping in an Innings** — `wk_best_innings`. ✅
5. **Captaincy Comparison** — `capt_compare` (tool at `/statistics/captaincy-compare`). ✅
6. **Captaincy by Season** — `capt_by_season`. ✅

Recorded **separately**: the **Best Bowling in a Match runs tie-break** correction (`bowl_best_match` now
ranks by most wickets, then fewest runs; genuine ties preserved; runs never invented when incomplete). ✅

## Approved decisions (2026-10-26)

- **Forfeit policy (§24.2a) — APPROVED and implemented.** A forfeit may count for **team** results,
  competition points and ladders (where competition rules recognise it); a forfeit with **no play** creates
  **no** player appearance and **no** captaincy appearance, and never inflates captaincy wins/losses/
  consecutive records/winning %. A **partly-played** match later awarded keeps its verified appearances and
  captaincy. Team outcomes and individual participation are kept separate. Implemented in `recalc.py`
  (`_forfeit_no_play`), applied consistently to statistics, records, profiles, captaincy reports and PDFs
  (they all read the one ledger), and covered by `tests/test_forfeit_policy.py` (full no-play forfeit,
  team-points-without-appearances, partly-played preservation, named-but-absent captain, captain in an
  awarded match, and a normal-match control).
- **Cricket Statz "Captain2" — EXCLUDED BY USER DECISION — NOT REQUIRED.** No Captain2 report or feature;
  no captaincy credit to Captain2. **Not** an outstanding requirement or open decision. Ordinary captaincy
  reports, statistics, comparisons and history are unaffected.

## Statistical-integrity corrections (2026-10-26)

- **Career bowling economy across mixed over lengths — FIXED.** Economy is computed from the actual legal
  balls bowled and **each match's own balls-per-over** (Law 17, from playing conditions — six-ball,
  eight-ball or any configured value), summed across the career. It never assumes one over length. A match
  whose over length is unrecorded is excluded from the economy and the figure is flagged
  (`economy_incomplete`); strike rate (balls ÷ wickets) is unaffected. Stored as `overs`/`overs_known` per
  bowling contribution in `recalc.py`; aggregated in `engine._bowl_row`. Covered by
  `tests/test_integrity_economy_keepers.py` (a 6-ball + 8-ball career → 3.44, not 3.00 or 4.00). Existing
  approved data should be recomputed (`/stats/recalc` backfill) to populate `overs`.
- **Multiple wicketkeepers in one innings — FIXED.** Keeper catches and stumpings are attributed to the
  **keeper who took them** (the recorded fielder), so where two players kept wicket in an innings each is
  credited with only their own dismissals (primary and second keeper both handled). A keeper dismissal
  whose fielder is unknown is **not** guessed or attributed to the primary keeper. Fixed in
  `records_detail.most_wk_dismissals_in_innings`; the keeper leaderboards already attributed by fielder.
  Covered by `tests/test_integrity_economy_keepers.py`.

## Remaining genuine limitations

- Boundaries (4s/6s), balls faced, and some fielder/bowler attributions depend on the scorecard recording
  them; where unrecorded the figure is a **known-minimum**, never zero.
- Consecutive-match streaks run over the team's **recorded played fixtures**; an undocumented missing
  fixture cannot be detected, and undated matches flag a **known-minimum** (never an assumed unbroken run).
