# 23. Complete RMCC Report Catalogue

**Deliverable 23 of 38** · §20, §21

Every mandatory RMCC report with its **exact counting methodology**. All reports come
from the one engine (deliverable 22): verified data only, unknown ≠ zero (known-minimum
flagged), no double counting, no invented statistics. Every match-record report is
available separately for **Home & Away**, **Finals (excl. Grand Finals)** and **Grand
Finals** (§20).

Thresholds are RMCC defaults (§21), workspace-configurable, and applied **only** to the
reports named (never to unrelated reports).

| Qualification | RMCC default |
|---|---|
| Batting Average | min **500 runs** |
| Batting Strike Rate | min **100 runs** |
| Bowling Average | min **50 wickets** |
| Bowling Economy Rate | min **50 wickets** |
| Bowling Strike Rate | min **50 wickets** |
| Captaincy Winning % | proposed min **20 eligible matches** `[DECISION D4]` |

## 23.1 Player careers

| Report | Counting methodology |
|---|---|
| Most Matches | Count distinct matches where `team_appearance.played = true` for the person (any grade/season unless filtered). |
| Most Consecutive Matches | Longest run of consecutive **team** matches (in chronological order within a grade/competition) in which the person played. Define "consecutive" against the team's match sequence, not the calendar. `[DECISION D9]` confirm sequence basis (team per grade). |
| Most Wins | Count matches played where the player's team result = win (exclude abandoned/no-result from the base; see result rules below). |
| Longest Serving | Span from first to last appearance (seasons represented); report in seasons and years. Uses appearances, not DOB. |
| Most Matches Played Together | For each **pair** of people, count matches where both have `played = true` in the same `match_team`. No double counting (unordered pair). Top pairs. |

## 23.2 Team streaks

Computed over the team's chronological match sequence (within grade/competition filter).

| Report | Methodology |
|---|---|
| Most Consecutive Matches Without a Loss | Longest run with no loss (wins, draws, ties count as "not a loss"). |
| Most Consecutive Matches Without a Win | Longest run with no win. |
| Most Consecutive Wins | Longest run of wins. |
| Most Consecutive Losses | Longest run of losses. |

**Outcome handling in streaks** `[DECISION D10 — open]` — each outcome type has a defined,
documented role, configurable where RMCC rules require:

| Outcome | Default streak behaviour |
|---|---|
| Win | counts as a win |
| Loss | counts as a loss |
| Draw / Tie | "not a loss" and "not a win"; continues the sequence, not a win/loss |
| Abandoned | skipped (does not count as win/loss); does not itself break a win/loss streak |
| No-result | skipped (as abandoned) |
| Forfeit | per the forfeit switch (deliverable 24 §24.2a) |
| **Missing historical fixture** | **a gap — it does NOT silently count as a win, a loss, or proof of an unbroken streak.** A streak spanning a known gap is reported as *known-minimum* and flagged |
| Unknown outcome | breaks the *known* sequence and is flagged; never assumed win/loss |

A streak is only asserted over a **contiguous, known** run; where the record is
incomplete the report says so rather than overstating an "unbroken" streak.

## 23.3 Batting

| Report | Methodology | Threshold |
|---|---|---|
| Top Run Aggregates | Σ runs across innings (known-minimum if any unknown). | — |
| Most Runs in a Season | Σ runs within one season. | — |
| Top Run Scores | Highest individual innings scores (list). | — |
| Most Runs in a Match | Σ a player's runs across all innings of one match. | — |
| Top Batting Averages | runs ÷ (innings − not-outs). | **min 500 runs** |
| Most Boundaries | Σ (4s + 6s) where known. | — |
| Most Sixes | Σ 6s. | — |
| Most Fours | Σ 4s. | — |
| Most 90s | Count innings with score in 90–99. | — |
| Most 40s | Count innings with score **40–49 inclusive**; 50+ excluded; separate from 50s/100s. `[DECISION D11 — recommended for final approval]` | — |
| Most Centuries | Count innings ≥ 100. | — |
| Most Half Centuries | Count innings 50–99 (confirm whether 100+ excluded — standard: 50–99). | — |
| Top Batting Strike Rates | (runs ÷ balls) × 100. | **min 100 runs** |
| Most Ducks | Count innings dismissed for 0 (score 0 **and** out; not-out 0 and unknown excluded). | — |
| Most Consecutive Scores Without a Duck | Longest run of completed innings without a duck. | — |

## 23.4 Batting partnerships

See deliverable 25 for exact partnership construction (from FoW / recorded partnerships /
batting entries; unknown-aware).

| Report | Methodology |
|---|---|
| Top Partnerships by Wicket | Highest partnership for each wicket (1st–10th). |
| Top Partnerships | Highest partnerships overall (any wicket). |
| Top Partnership Aggregates | Σ partnership runs for a **pair** across matches (unordered pair; no double counting). |

## 23.5 Bowling partnerships

**Methodology CONFIRMED** (`[DECISION D12 — RESOLVED]`, 2026-10-21). Full definition,
formula and worked example in [25-partnership-calculation.md](25-partnership-calculation.md)
§25.3. Summary: for each unordered combination, sum the **bowler-credited** wickets of all
members across the matches in which **every** member participated; count each match once
(innings summed); rank by combined total; run-outs excluded; verified figures, known-
minimum where incomplete.

| Report | Methodology |
|---|---|
| Most Wickets as a Bowling Partnership — 2 players | Combination = any 2 players; qualifying matches = both played; total = Σ their bowler-credited wickets across those matches. |
| — 3 players | Same rules, combinations of 3 (all three must have played the match). |
| — 4 players | Same rules, combinations of 4 (all four must have played the match). |

Display per combination: member names, total combined wickets, matches played together,
average combined wickets per match, first/last qualifying match, supporting records. A
member who played but took 0 wickets still qualifies; a match with any member absent is
excluded. Classification splits (§23.10) apply.

## 23.6 Bowling

| Report | Methodology | Threshold |
|---|---|---|
| Top Wicket Takers | Σ wickets. | — |
| Top Bowling Averages | runs conceded ÷ wickets. | **min 50 wkts** |
| Most Wickets in a Season | Σ wickets in one season. | — |
| Best Bowling in a Match | Best (most wickets, then fewest runs) across a match. | — |
| Top Economy Rates | runs ÷ overs. | **min 50 wkts** |
| Top Bowling Strike Rates | balls ÷ wickets. | **min 50 wkts** |
| Most Expensive Bowling in an Innings | Highest runs conceded in one innings spell. | — |
| Most 5-Wicket Innings | Count innings with ≥ 5 wickets. | — |
| Most Ducks Inflicted | Count dismissals where the bowler dismissed a batter for 0 (bowler credited; run-outs excluded). | — |

## 23.7 Fielding & wicketkeeping

| Report | Methodology |
|---|---|
| Top Fielder–Bowler Combinations | Count dismissals crediting a specific (fielder, bowler) pair (catches; stumpings for keeper). No double counting. |
| **Top Catches (fielding)** | Σ catches taken **as a fielder, excluding catches taken while keeping wicket**. `[DECISION D13 — recommended, requires approval]` |
| **Top Wicketkeeper Catches** | Σ catches taken **while acting as wicketkeeper** (separate report). |
| **Top Wicketkeeper Stumpings** | Σ stumpings. |
| **Top Wicketkeeper Dismissals (total)** | keeper catches + stumpings. |
| Top Wicketkeeping in an Innings | Most keeper dismissals in one innings. |
| **Combined Catches (optional)** | fielding + keeper catches, user-selected; **no double-counting** of any dismissal. |
| Top Run Outs | Σ run-outs credited. |

Where the fielder or wicketkeeper is **unknown** (e.g. Cricket Statz `Fielder=0`,
deliverable 16a), the dismissal is **not guessed** or attributed — it is excluded from
these reports (unknown ≠ zero).

## 23.8 Captaincy

Full specification in deliverable 24. Reports: Most Matches Captained; Most Wins as
Captain; Best Winning % as Captain (min 20, `[DECISION D4]`); Most Grand Finals
Captained; Most Grand Final Wins as Captain; Most Consecutive Wins as Captain; Captaincy
by Season; Captaincy by Grade; Captaincy Win/Loss/Draw/Tie Record; Captaincy unbeaten &
winless streaks.

## 23.9 Other records

| Report | Methodology |
|---|---|
| Annual leading run scorers | Top run-scorer per season. |
| Annual leading wicket takers | Top wicket-taker per season. |
| Best single-season run totals | Highest season aggregates (all-time list). |
| Best single-season wicket totals | Highest season wicket aggregates. |
| Highest innings & match performances | Best individual innings / match performances. |
| Highest partnerships by wicket | (deliverable 25) |
| Grand Final records | All above restricted to `classification = grand_final`. |
| Player milestones | deliverable 26. |
| Career achievements | deliverable 26. |

## 23.10 Classification splits (mandatory)

Every match-record report supports three scopes via `match.classification`:

- **Home & Away** (regular season)
- **Finals** — finals **excluding** Grand Finals
- **Grand Finals**

Plus an "All" combined scope. The split is a filter on the same engine metric, so no
logic is duplicated. Where a report is inherently all-time (e.g. Longest Serving), the
split is offered where meaningful.

## 23.11 Qualification rules

- Thresholds apply **only** to the averages/rates/captaincy-% reports listed in §21, never
  to aggregates/counts.
- Below-threshold players are shown in a separate "unqualified" view, never silently
  dropped from the underlying data.
- Known-minimum entries (deliverable 22) are flagged in every report and can be
  shown/hidden.
