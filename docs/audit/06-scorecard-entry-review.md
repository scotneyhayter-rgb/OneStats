# Audit — Scorecard Entry Review (CricketStatz ↔ OneStats)

**Part 6 / Deliverable F deep-dive.** Compares entering and correcting a scorecard in both apps. CricketStatz
observations are from its live **Edit Match** screen earlier this session (the session has since logged out, so
some per-field flow is from the observed screen + the known data model, marked *observed/model*); OneStats is
from its code (`ScorecardEditor.tsx`, `grids.tsx`, `scorecard-logic.ts`, `PersonWizard.tsx`).

## The two models
- **CricketStatz**: a mature web scorer. *Edit Match* = innings (batting team, totals, **innings-level
  extras** Byes/Legbyes/Noballs/Wides), a Results block (toss, result, sub-result, margin with a **Calc**
  button), and per-batter rows (Batpos, Batsman, **Howout**, **Fielder**, **Bowler**, Score, Balls, mins, 4s,
  6s, with **fall-of-wicket embedded per batter**). Also offers **live ball-by-ball scoring** from any device
  and an **Innings Override** (runs/wickets) + a **Runouts/Unassigned Wickets** box. Entry errors are caught
  *after the fact* by its ~20 data-quality reports.
- **OneStats**: a completed-card editor over the one match model, with an approval workflow. Batting grid
  (Batter / How out / Fielder / Bowler / R …), bowling grid, fall-of-wickets, partnerships, and an innings
  score header distinguishing official vs calculated vs unknown.

## Feature-by-feature

| Capability | CricketStatz | OneStats | Verdict |
|---|---|---|---|
| **Inline player creation** during entry | Players generally established up front | **PersonWizard** creates a player mid-entry with validation + identity matching | ✅ OneStats |
| **Real-time validation** | Data-quality **reports**, run after entry | **In-grid advisories** as you type — FOW gaps, batting-order anomalies, duplicate batter/position — non-blocking, no server round-trip | ✅ OneStats (catch at entry, not later) |
| **Fall of wickets** | Embedded per batter (observed/model) | FOW grid + per-row advisories + inline highlight | ≈ / ✅ OneStats on validation |
| **Partnerships** | Derivable from FOW | **Auto-generated** from FOW, editable | ✅ OneStats |
| **Multi-fielder run-outs** | Single `Fielder` field | Primary fielder + **"+ add fielder"** (assists), one wicket, never double-counted | ✅ OneStats (richer model) |
| **Unknown / known-minimum** | Innings Override; some fields assumed | Unknown preserved (e.g. unknown balls → SR flagged, not inflated); never zero-filled | ✅ OneStats (honesty) |
| **Correction safety** | Direct edit | **Draft → approved** workflow, audit log, reversible identity merges, provenance | ✅ OneStats |
| **Innings-level extras** | Byes/Legbyes/Noballs/Wides at innings | Same (innings extras) | ≈ |
| **Result / margin** | Margin **Calc** button | Result derived from innings/outcome | ≈ |
| **Live ball-by-ball scoring at the ground** | **Yes** — score live from any device, with commentary | No — enters completed cards | ⚠ **CricketStatz** (a genuine gap) |

## Findings
1. **OneStats' entry is the more modern, safer experience for completed cards**: inline advisories catch scorer
   mistakes *as you type* (where CricketStatz surfaces them later as reports), players can be created in place,
   partnerships auto-derive, multi-fielder run-outs are modelled, and the draft→approved + audit + reversible-
   merge workflow protects historical data. Unknown values stay unknown rather than being assumed.
2. **CricketStatz's one clear advantage is live scoring** — ball-by-ball from a device at the ground, which
   OneStats does not do. For a club scoring games live, this is a real capability gap.
3. Minor CricketStatz conveniences worth matching: a one-click **margin Calc** on results, and an **innings
   override** for a known total when the card is incomplete (OneStats shows official-vs-calculated but a direct
   "official total" override entry could be smoother).

## Recommendations (roadmap)
- **P3/UX:** add a **result-margin auto-calc** button and make the **official-total override** a first-class
  field on the innings header (small, high-frequency wins). *Low effort.*
- **P4 (large):** evaluate **live ball-by-ball scoring** (the CricketStatz capability OneStats lacks) — a
  significant feature; scope separately. Until then, OneStats remains the stronger *post-match* editor.
- **Keep** the inline-advisory + approval model as a headline strength; consider surfacing a per-card
  "data-quality check" button that runs the new `data_quality` checks against the single match being edited
  (closing the loop between entry and the linting suite).

## Net
For entering and correcting a **completed** scorecard, OneStats is already ahead — safer, more validating, and
more honest about unknowns. CricketStatz leads only on **live, at-the-ground scoring**, which is the one
scorecard-related capability OneStats should weigh adding.
