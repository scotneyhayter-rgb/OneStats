# 24. Captaincy Calculation Specification

**Deliverable 24 of 38** · §20 captaincy, §21

Exact methodology for captaincy statistics. Deterministic, verified-data-only,
unknown-aware (deliverable 22).

## 24.1 Who is "the captain" for a match

- The captain of a `match_team` is `match_team.captain_person_id`. An **acting captain**
  (`acting_captain_person_id`) is credited when recorded as actually leading the side.
- `[DECISION D14]` When both a captain and acting captain are recorded for one side in
  one match, which is credited for captaincy stats? **Recommendation:** credit the person
  who actually captained (acting captain if present for that match), and expose both;
  never double-credit the same match to two captains.
- Matches with an **unknown** captain are excluded from captaincy counts (unknown ≠ zero),
  not attributed to anyone.
- **Cricket Statz "Captain2":** **EXCLUDED BY USER DECISION (2026-10-26) — NOT REQUIRED.** The user has
  decided OneStats will not implement a Captain2 report or any equivalent Captain2 captaincy feature. The
  nullable `match_team.captain2_person_id` column may remain for raw import fidelity, but **no captaincy
  credit is ever assigned to Captain2**, and a single match is **never double-credited** to two captains
  (§24.1). This is **no longer an open question** and is not an outstanding requirement. All ordinary
  captaincy reports, statistics, comparisons and history are unaffected.

## 24.2 Winning percentage (§20 exact rule)

> **Winning % = wins ÷ eligible matches captained × 100.**

- **Eligible matches** exclude **abandoned** matches and **no-results** from the default
  denominator.
- **Forfeits** are handled per documented competition rules (`[DECISION D15]` — e.g. a
  forfeit win/loss counts, or is excluded; default proposal: a forfeit with a defined
  winner counts as a win/loss, a double-forfeit/no-contest is excluded).
- Draws and ties are eligible matches (in the denominator) but are not wins.
- **Configurable minimum matches** to qualify for the Winning % report; **proposed RMCC
  default = 20 eligible matches** `[DECISION D4]`.

```text
wins               = matches captained with team result = win
eligible           = matches captained
                     − abandoned − no_result
                     ± forfeits (per competition rule, D15)
winning_percentage = wins / eligible * 100      (eligible > 0; else "insufficient data")
```

## 24.2a Configurable forfeit treatment (cross-cutting) `[DECISION D15 — open]`

A forfeited match is **not** assumed equivalent to a fully played match. Forfeit
treatment is **configurable per workspace/competition** and applied consistently across
every area it touches, because the right answer depends on RMCC's documented rules
(which the user must supply — §37.3). Each of these is a separate configurable switch:

| Area | Configurable question |
|---|---|
| Player appearances | Does a forfeit count as a match played for the listed players? |
| Wins/losses (team & player) | Does a defined-winner forfeit count as a win/loss? |
| Captaincy matches & wins | Is the captain credited with a forfeit match/win? |
| Winning % denominator | Is a forfeit an *eligible* match (§24.2)? |
| Team streaks (§23.2) | Does a forfeit extend/break a streak, or is it skipped? |
| Player records/aggregates | Are performances in a forfeit (if any) counted? |

Default proposal (pending RMCC rules): a forfeit **with a defined winner** counts as a
win/loss for team and captain but players get **no batting/bowling performances**; a
double-forfeit/no-contest is excluded everywhere. **Do not finalise until the user
confirms the RMCC rule.**

## 24.3 Report definitions

| Report | Methodology |
|---|---|
| Most Matches Captained | Count matches where person is the credited captain. |
| Most Wins as Captain | Count credited-captain matches with result = win. |
| Best Winning % as Captain | Formula above; **min 20 eligible** (configurable). |
| Most Grand Finals Captained | Credited-captain matches with `classification = grand_final`. |
| Most Grand Final Wins as Captain | …and result = win. |
| Most Consecutive Wins as Captain | Longest run of wins over the captain's chronological captained-match sequence. |
| Captaincy by Season | Captained-match counts/results grouped by season. |
| Captaincy by Grade | …grouped by grade. |
| Captaincy Win/Loss/Draw/Tie Record | Tally of each result type among captained matches. |
| Captaincy unbeaten streak | Longest run of captained matches without a loss. |
| Captaincy winless streak | Longest run of captained matches without a win. |

## 24.4 Classification splits

Captaincy reports support Home & Away / Finals (excl. GF) / Grand Finals / All
(deliverable 23 §10), via `match.classification`.

## 24.5 Unknown & integrity handling

- Matches with unknown result are excluded from win/loss tallies and from the Winning %
  denominator (not counted as anything).
- Streaks are computed over the ordered sequence of the captain's captained matches;
  matches with unknown result **break the known sequence** and are flagged, rather than
  being assumed wins or losses (`[DECISION D10]` consistency).
- No match is double-counted across two captains.
