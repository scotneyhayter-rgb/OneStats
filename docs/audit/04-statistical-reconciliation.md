# Audit Deliverable E — Statistical Accuracy Reconciliation

**Stage 4.** Actual numerical comparison of OneStats (computed live from its database) against CricketStatz
(the trusted benchmark, read live from its `/ss/rrj` report JSON on 2026-11-01). Per Part 15 rule 15, this
is based on **real CricketStatz numbers**, not assumptions or internal tests.

## Method
- CricketStatz figures pulled from the RMCC account (club 26267): Top Run Aggregates (mode 4) and Top Wicket
  Takers (mode 5), scoped to the club, all-time.
- OneStats figures computed from the live DB via the one engine (`batting_leaders` / `bowling_leaders`),
  scoped to the RMCC organisation — the same population.
- Players matched by "Lastname Initial"; the top, distinctively-named players were used to avoid identity
  ambiguity (two different "Robinson R" etc. exist — an identity caveat, not a calc issue).
- Each comparison classified: **PARITY** (raw inputs AND computed stat match), **SOURCE DIFF** (raw inputs
  differ → stale import / recent CricketStatz edits), **CALC DEFECT** (raw inputs match but the computed stat
  differs → a formula bug to fix).

## Results

**19 comparisons · 17 exact PARITY · 2 SOURCE DIFF · 0 CALC DEFECTS.**

### Batting (10 players — runs, innings, not-outs, average)
| Player | OneStats | CricketStatz | Verdict |
|---|---|---|---|
| O'Brien M | 7048 / 377 / 30 / 20.31 | 7048 / 377 / 30 / 20.31 | **PARITY** |
| Bond T | 5921 / 248 / 22 / 26.20 | same | **PARITY** |
| Quick T | 5459 / 266 / 34 / 23.53 | same | **PARITY** |
| Robinson D | 4023 / 111 / 12 / 40.64 | same | **PARITY** |
| Hayter S | 3721 / 183 / 8 / 21.26 | same | **PARITY** |
| Armstrong M | 3197 / 117 / 24 / 34.38 | same | **PARITY** |
| Quick N | 3085 / 216 / 26 / 16.24 | same | **PARITY** |
| Skrabl P | 3016 / 147 / 20 / 23.75 | same | **PARITY** |
| Dean M | 1542 / 211 / 40 / 9.02 | same | **PARITY** |
| Taylor D | 5565 / 306 / 28 / 20.02 | 5591 / 307 / 28 / 20.04 | SOURCE DIFF (the match added since the Oct export) |

### Bowling (9 players — wickets, balls, runs, average, economy)
| Player | OneStats | CricketStatz | Verdict |
|---|---|---|---|
| O'Brien M | 461 / 10569 / 7285 / 15.80 / 4.14 | identical | **PARITY** |
| Boyd K | 388 / 6099 / 3786 / 9.76 / 3.72 | identical | **PARITY** |
| Taylor D | 330 / 9318 / 5747 / 17.42 / 3.70 | identical | **PARITY** |
| Dean M | 270 / 8110 / 4875 / 18.06 / 3.61 | identical | **PARITY** |
| Quick N | 265 / 7231 / 4306 / 16.25 / 3.57 | identical | **PARITY** |
| Skrabl P | 245 / 9042 / 4671 / 19.07 / 3.10 | identical | **PARITY** |
| Armstrong M | 199 / 5551 / 2632 / 13.23 / 2.84 | identical | **PARITY** |
| Hayter S | 46 / 1502 / 932 / 20.26 / 3.72 | identical | **PARITY** |
| Cosgriff D | 327 / 9879 / 5369 / 16.42 / 3.26 | 330 / 9894 / 5370 / 16.27 / 3.26 | SOURCE DIFF (recent edits; econ still matches) |

## Findings
1. **OneStats' batting and bowling calculations are in exact agreement with CricketStatz.** Batting average
   (runs ÷ dismissals), bowling average (runs ÷ wickets) and **economy** all match to the decimal on every
   player whose raw inputs match — **no calculation defect found**. This is a benchmark-verified result.
2. **Economy parity** is notable: for these (mostly modern, 6-ball-era) careers OneStats' true-over-length
   economy matches CricketStatz's balls÷6 exactly. The documented career-economy approximation only diverges
   for heavy 8-ball-era careers; none surfaced in the top cohort. (Flagged for a targeted 8-ball check later.)
3. **The only two differences are SOURCE, not calc**: Taylor D (batting +26 runs / +1 innings) and Cosgriff D
   (bowling +3 wkts) reflect data entered in CricketStatz *after* the October export OneStats was built from —
   the same staleness the fielder-refresh backfill (commit f0b3bff) addresses. A fresh re-import closes them.
4. **Fielding (catches / run-outs / stumpings)** is the one area with known SOURCE differences — the export
   dropped the fielder on ~760 run-outs and ~1,000 catches (Deliverable, run-out analysis + data-quality scan:
   1,037 missing fielders). This is import staleness, not a calc defect; the fielder backfill resolves it on
   re-import. The fielding *formulas* (catch = field+keeper, keeper dismissals separate, run-out credit) were
   verified correct in the engine tests.

## Conclusion (Stage 5)
No statistical calculation defects were found in batting or bowling against the CricketStatz benchmark — the
engine is accurate; remaining differences are source-data staleness, resolved by a fresh re-import + the
fielder backfill. The earlier run-out attribution issue was the one real data-side defect and is fixed.
Identity ambiguity (duplicate "Lastname Initial") is a matching caveat for a future per-source-ref reconcile,
not an engine error.
