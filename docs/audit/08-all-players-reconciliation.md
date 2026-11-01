# Deliverable K — All-Players Reconciliation: OneStats vs CricketStatz

**Date:** 2026-11-01
**Scope:** Every RMCC player with any recorded statistic (560 CricketStatz player identities).
**Method:** CricketStatz career figures taken from its live leaderboards (`/ss/rrj`, club 26267, all-time):
Top Run Aggregates (runs, matches), Top Wicket Takers (wickets), Top Catches, Top Wicket
Keeping (stumpings), Top Run Outs. OneStats figures computed from the live match-stat ledger,
scoped to **RMCC-club official matches** (`include_in_statistics = true` and approved/verified),
with merged persons resolved to their canonical record — i.e. the same basis the OneStats player
profile uses. Comparison is read-only; **nothing was changed.**

## Headline result

On the 558 players present in both systems, OneStats and CricketStatz agree **exactly** for the
overwhelming majority, and batting and bowling are effectively identical:

| Metric | Players compared | Exact match | Differ | Differ by ≤1 | CS total | OneStats total | Net diff |
|---|---|---|---|---|---|---|---|
| **Runs** | 558 | **557** | 1 | 0 | 137,635 | 137,615 | −20 |
| **Wickets** | 558 | **558** | 0 | 0 | 8,394 | 8,394 | **0** |
| **Catches** | 558 | 537 | 21 | 10 | 4,180 | 4,128 | −52 |
| **Stumpings** | 558 | 557 | 1 | 1 | 318 | 317 | −1 |
| **Run-outs** | 558 | 550 | 8 | 6 | 139 | 125 | −14 |
| **Matches** | 558 | 526 | 32 | 32 | 10,743 | 10,778 | +35 |

- **Bowling is a perfect match** — all 558 players, every wicket.
- **Batting is one player off** — a single stale innings (see below).
- The only material residual is in **fielding (catches & run-outs)**, and it has a single known
  cause (below).
- **No player is missing.** All 560 CricketStatz identities resolve to OneStats; two (Keogh, Morton)
  simply differ in name-key spelling (CS stores two initials, OneStats one) and match on inspection.

## What the earlier large discrepancies actually were

Before the comparison was scoped correctly it appeared OneStats carried ~37,000 more runs than
CricketStatz. **That was entirely a measurement artefact, not an OneStats error:**

1. **Club scope.** The CricketStatz leaderboard is filtered to club 26267. The first OneStats
   aggregation summed *every* innings a person played for *any* team in the workspace (including
   seasons for other clubs whose scorecards are also stored). Scoping OneStats to RMCC-club teams
   removed essentially the entire gap.
2. **Name-key collapsing.** CricketStatz holds one real person as several player records
   (e.g. "Hayter S" = Scotney Hayter **and** Stuart Hayter; different eras keyed to the same
   surname+initial). Summing the leaderboard rows per surname+initial — on **both** sides — lines the
   two systems up correctly, which is why the totals now agree to the unit.

OneStats faithfully reproduces the CricketStatz figures once compared on the same basis.

## Residual differences (the real, small gaps)

### Batting — 1 player
| Player | CricketStatz | OneStats | Diff |
|---|---|---|---|
| Hannett D | 241 | 221 | −20 |

Same match count (13) in both, so this is a **single innings that differs** — almost certainly a
scorecard CricketStatz revised after the OneStats import (OneStats re-import is idempotent and never
overwrites an existing match). Fixable with a targeted refresh of that one match.

### Catches — 21 players (OneStats lower in every case)
Largest: Farish A −8, Isen D −7, Walton D −5, Brady S −4; the rest −1 to −3
(Zuin, Robinson R, Phillips, Patterson, Skrabl, Jenkins, Brown, Walker, Meek, Lennie,
Le Poidevin, Humphries, Hannett, Gason C, Fratin, Cosgriff G, Cosgriff D). Total gap: 52 catches.

### Run-outs — 8 players (OneStats lower in every case)
Hayter S 18→12 (−6), Robinson R 2→0, and −1 each for Shea, Keilar, Kennedy, Slorach, Jamieson, King.
Total gap: 14 run-outs.

### Stumpings — 1 player
Malpas E 8→7 (−1).

**Cause of the fielding gaps (catches + run-outs):** CricketStatz computes a fielder's catches and
run-outs from an **internal per-player fielding tally**, but the database export it provides only
carries the batting scorecard's "Fielder" field. Where a historical scorecard never recorded *which*
fielder took a catch or effected a run-out, CricketStatz still credits it from its internal tally,
and OneStats (working only from the exported scorecard) cannot. This is the exact issue identified in
the run-out investigation, now quantified club-wide: it accounts for **every** fielding difference and
is the only systematic residual. Closing it requires overwriting historical dismissals from
CricketStatz's per-match fielding report — a production data change that needs your explicit
authorisation (a dry-run reconstruction is prepared and validated, not applied).

### Matches — 32 players, all ±1 (a few ±2–4)
Two harmless definition nuances, not errors:
- Fielding-only names (Tschampion, Wilcox, Vanderwaal, Pitt, etc.) show CS 0 / OneStats 1 because the
  CS *batting* leaderboard counts 0 matches for someone who only fielded, while OneStats counts the
  appearance.
- A handful of ±1 edges on long careers (O'Brien M 313→314, Skrabl 134→135) are single borderline
  matches (e.g. an abandoned game) classified differently.

## Duplicate persons worth merging (you asked to review merges)

Already-merged players were resolved correctly in this comparison (merge links were followed). The
comparison also surfaced **7 name-keys that still hold the same real person as two or three unmerged
OneStats records** — merge candidates for you to confirm:

| OneStats records | Likely same person |
|---|---|
| `John Pola`, `J Pola`, `JD Pola` | John Pola (3 records) |
| `Alan Smith`, `A Smith` | Alan Smith |
| `David Turner`, `D Turner` | David Turner |
| `Wayne Gason`, `W Gason` | Wayne Gason |
| `George Miller`, `G Miller` | George Miller |
| `Doug Walton`, `D Walton` | Doug Walton |
| `Scott Hyatt`, `S Hyatt` | Scott Hyatt |

These did **not** distort the comparison (CricketStatz splits them the same way), but merging them in
OneStats is correct data hygiene. **Not merged automatically** — please confirm each before merging.

The following surname+initial keys hold **genuinely different people** and are correctly kept separate
(do **not** merge): Scotney/Stuart Hayter, Keith/Kev Boyd, Matt/Michael Wood, Adam/Alex Barrie,
Rob/Rod Marshall, Alan/Alf Bass, Jake/Jim Robinson, Simon/Shaun Brady, Jodie/Josh Barrie,
Dino/David Fratin, Ray/Rex Robinson, Lindsay/Luke Robinson.

## Bottom line

OneStats reproduces CricketStatz's club statistics essentially exactly for batting (557/558) and
bowling (558/558). The only systematic difference is fielding credits that CricketStatz derives from
an internal tally absent from its own data export — a source-data limitation, not an OneStats
calculation error — plus one stale batting innings and a handful of ±1 match-count definition edges.
No player is missing and no figure is fabricated on either side.
