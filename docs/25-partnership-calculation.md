# 25. Partnership Calculation Specification

**Deliverable 25 of 38** · §20 partnerships

Exact methodology for batting and bowling partnerships. Deterministic, verified-data-only,
unknown-aware, no double counting (deliverable 22).

## 25.1 Batting partnerships — construction

A batting partnership is the stand between two batters for a given wicket in an innings.
Source of truth, in priority order:

1. **Recorded partnership** (`partnership` row) if the source provides it — use directly
   (runs, balls, unbroken), with provenance.
2. Otherwise **derive** from **fall-of-wicket** data: partnership for wicket *n* = runs
   between FoW *n−1* and FoW *n* (1st wicket from 0). The pair = the two batters at the
   crease over that span, reconstructed from batting order + FoW `person_out`.
3. If neither recorded partnership nor sufficient FoW exists, the partnership is
   **unknown** — not zero, not estimated (unknown ≠ zero).

```text
partnership_runs(wicket n) = FoW[n].runs - FoW[n-1].runs     (FoW[0].runs = 0)
last (unbroken) partnership = innings_total - FoW[last].runs  (if innings complete & known)
```

- **Unbroken** partnerships (not ended by a wicket) are marked `unbroken = true`.
- Pairs are **unordered** — (A,B) = (B,A) — to avoid double counting in aggregates.

## 25.2 Batting partnership reports

| Report | Methodology |
|---|---|
| Top Partnerships by Wicket | For each wicket 1–10, the highest partnership runs across all innings. |
| Top Partnerships | Highest partnerships regardless of wicket. |
| Top Partnership Aggregates | Σ partnership runs per unordered pair across matches; known-minimum if any stand unknown. |

Classification splits (Home & Away / Finals / Grand Finals) apply (deliverable 23 §10).

## 25.3 Bowling partnerships — CONFIRMED method `[DECISION D12 — RESOLVED]`

The user confirmed the definitive OneStats method (2026-10-21). It is a
**participation-based combination** method: a combination's "partnership wickets" is the
sum of the wickets each member was credited with, across the matches in which **every**
member participated. This is computable from standard scorecards (no over-by-over
sequence required) and applies identically to 2-, 3- and 4-player combinations.

### Calculation rules (definitive)

1. Identify every unique combination of **two, three or four** players (unordered; a
   player appears once per combination).
2. Find all **eligible/qualifying matches** — matches in which **every** member of the
   combination participated (`team_appearance.played = true`).
3. For each qualifying match, **add together the wickets officially credited to those
   members** (bowler-credited dismissals only).
4. **Exclude** any match where **any** member did not participate.
5. A member who participated but took **zero wickets still qualifies** (the match still
   counts; they contribute 0).
6. **Aggregate** the combined wickets across all qualifying matches.
7. **Rank** combinations by total combined wickets taken while playing together.
8. **Display** per combination: all member names · total combined wickets · matches
   played together · average combined wickets per match (`total ÷ matches together`) ·
   first and last qualifying match · supporting match records (drill-down).
9. **Exclude run-outs and any dismissal not credited to a bowler.**
10. Respect **workspace, club, competition, grade, season and match-classification**
    filters (Home & Away / Finals / Grand Finals / All — deliverable 23 §10).
11. **Count each match once per combination**, including **multi-innings** matches — a
    member's wickets are summed across all innings of that match, but the match counts as
    **one** toward "matches played together".
12. Use **verified bowling figures**; **distinguish incomplete/missing historical bowling
    figures from a confirmed zero** (known-minimum, deliverable 22) — a missing figure is
    unknown, not 0.
13. Members need **not** have bowled **simultaneously** or in the **same innings** —
    participating in the same match is the only requirement (rule 2). Also confirm all
    nominated players appeared for the **same team** in that match.

```text
members           = unordered set of 2, 3 or 4 people
qualifying_match  = match where every member has played = true
combo_wickets(m)  = Σ over members of (bowler-credited wickets for that member in match m,
                    summed across all innings of m; run-outs/non-bowler dismissals excluded)
total_wickets     = Σ over qualifying_matches of combo_wickets(m)
matches_together  = count(qualifying_matches)           # each match once
avg_per_match     = total_wickets / matches_together     # matches_together > 0
```

### Worked example

Combination {A, B}. A & B both played matches M1, M2, M4 (not M3 — B absent).
- M1: A 3 wkts, B 0 wkts → 3 (B qualifies on 0, rule 5)
- M2 (two innings): A 1+2, B 2+1 → 6 (rule 11 sums innings, match counts once)
- M3: excluded (B did not play, rule 4)
- M4: A 0, B 4 → 4

`total_wickets = 3 + 6 + 4 = 13`; `matches_together = 3`; `avg_per_match = 4.33`.
First/last qualifying match = M1 / M4.

**User-confirmed 3-player example** — combination {A, B, C}:

| Match | A | B | C | Qualifies? | Combined wickets |
|---|--:|--:|--:|---|--:|
| 1 | 4 | 3 | 2 | Yes | 9 |
| 2 | 5 | did not play | 1 | **No** (B absent) | excluded |
| 3 | 2 | 4 | 3 | Yes | 9 |
| 4 | 0 | 4 | 2 | Yes (A on 0 still qualifies) | 6 |

`total_wickets = 24` across `matches_together = 3`; `avg_per_match = 8.0`.

### Notes

- A run-out in which a member was the fielder is **not** counted (rule 9) — only
  bowler-credited wickets.
- 3- and 4-player combinations use the same rules; the "all members participated"
  requirement (rule 4) naturally makes larger combinations rarer and is applied
  identically.
- Combinations are unordered, so no combination is double-counted; within a match a
  wicket credited to one bowler is counted once (it belongs to that member's figure).

## 25.4 Unknown handling (batting and bowling partnerships)

- A wicket with an **unknown bowler** is excluded from bowling-partnership credit
  (not attributed, not zeroed).
- For bowling combinations, a qualifying match in which a member's bowling figures are
  **unknown/incomplete** is flagged so the combination's total is reported as a
  **known-minimum** (deliverable 22), distinct from a confirmed total; it is never
  silently treated as 0.
- A batting stand with unknown runs is excluded from aggregates (known-minimum flagged).
- The engine never fabricates a partnership where the underlying data is insufficient.

## 25.5 Feasibility against the real Cricket Statz data (deliverable 16a)

Verified against the real RMCC export (16a.10): **fall-of-wicket is reliably
reconstructable** from `FOWPos`/`FOW`/`FOWBatID` — for the sampled innings the JSON
reproduced the UI fall-of-wicket list exactly (31,36,40,63,70,94,108,160). Therefore:

- **Highest partnerships, partnerships by wicket, and partnership aggregates are feasible**
  for innings with complete FOW.
- Where FOW is **incomplete** (fewer entries than wickets, or the CS "FOW List Incomplete"
  flag — which is itself absent from the export and must be inferred), partnerships are
  reported as **incomplete / known-minimum**, and **missing partners or scores are never
  invented** (the user's explicit instruction).
- Cricket overs and the absence of ball-by-ball do not affect run-based partnership
  reconstruction (balls-per-partnership are usually unknown and left so).
