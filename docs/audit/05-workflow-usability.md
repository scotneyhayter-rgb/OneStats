# Audit Deliverable F — Workflow & Usability Assessment

**Stage 6 (Part 10).** Common tasks compared between CricketStatz (benchmark) and OneStats, from direct use
of both. Step counts are observed estimates (clicks/fields from a logged-in start on the relevant screen),
not lab-timed. Goal: make OneStats simpler for volunteers and more powerful for statisticians.

Legend: **✅ OneStats better · ≈ parity · ⚠ OneStats weaker · ✚ design opportunity**

| # | Task | CricketStatz | OneStats | Verdict |
|---|---|---|---|---|
| 1 | Find a player's career stats | Players → open player → profile (~2–3) | People → Details → "View full career profile" (~3) | ≈ — OneStats profile is richer (badges, milestones, per-season) |
| 2 | All-time batting report | Reports → pick "Top Run Aggregates" from ~230 list → Run (~3) | Statistics → Batting tab (default) (~1) | ✅ fewer steps; catalogue for the long tail |
| 3 | Filter to one grade | Reports form → Grade (multi-select) → Run (~2) | Statistics → pick a Competition → Grade (~2) | ≈ (OneStats grade needs a competition first; CricketStatz grade is top-level) ⚠ minor |
| 4 | Compare two seasons | Run the report twice with different Season, read side by side (~6) | Run twice, or Seasonal Leaders; no two-season side-by-side (~6) | ✚ neither has a true season-vs-season compare |
| 5 | Performances vs one opposition | Reports form → Opposition → Run (~2) | Statistics → Opposition selector → (~2) *(shipped this audit)* | ≈ — now parity (was ⚠ before the opposition filter) |
| 6 | Captaincy report | Reports → a captaincy report → Run (~3) | Statistics → Captaincy tab (~1); plus by-season + comparison | ✅ richer captaincy suite |
| 7 | Historical partnership record | Reports → Top Partnerships → Run (~3) | Report Catalogue → Partnerships (highest / by wicket / aggregates) (~3) | ≈ |
| 8 | Enter a scorecard | Matches → new → Edit Match (innings/results/cards) | Matches → New match → scorecard editor (inline validation, auto FOW/partnerships) | ✅ richer validation + known-minimum honesty |
| 9 | Correct a scorecard | Open Edit Match, change fields | Open match, edit; approval workflow + audit + reversible identity merges | ✅ safer (audit, provenance, reversible) |
| 10 | Export a report | Report page → print/JSON/embed | Any report → PDF (branded) / CSV, figures identical to screen | ≈ (CricketStatz leans to web-embed; OneStats to branded PDF) |
| 11 | Find a match from a season | Matches list, filter | Matches screen grouped by season + season filter + "View matches from this season" (~2) *(shipped this audit)* | ✅ |
| 12 | Compare two players | No dedicated compare; read a leaderboard | Captaincy comparison exists; no general two-player batting/bowling compare | ✚ **build a Player Compare** — a clear OneStats win neither app has |
| 13 | Identify missing records / data errors | ~20 data-quality reports | Research Centre gaps + **Data Quality tab** (8 checks, drill-down) *(shipped this audit)* | ≈/✅ — now comparable, with click-to-fix |
| 14 | Create a filtered public report | Embed report HTML in a site | Saved reports + publishing snapshot (approved stats only) | ≈ — OneStats keeps approval/privacy control |

## Key usability findings
- **OneStats is faster for the common case** (tasks 2, 6, 8, 11): the default Statistics tabs and the
  season-grouped Matches screen put the everyday report one click away, where CricketStatz routes everything
  through the ~230-report picker + filter form.
- **OneStats leads on safety** (tasks 8, 9): approval workflow, audit log, reversible identity merges, and
  honest known-minimum / unknown handling — CricketStatz edits are more direct but less protected.
- **CricketStatz leads on raw breadth and one grade-pick** (tasks 1, 3): its single top-level filter form and
  flat report list make an obscure report or a bare grade filter reachable without first choosing a
  competition. OneStats' grade is nested under a competition (task 3) — a small friction to smooth.

## Recommendations (for the roadmap)
1. ✚ **Player Compare** (task 12) — a two/multi-player side-by-side on batting/bowling/fielding using the same
   filters. Neither app has it; a clear differentiator. *High value, medium effort.*
2. ✚ **Season-vs-season compare** (task 4) — a compact two-column season comparison for a player or team.
3. ⚠ **Grade without a competition** (task 3) — allow a top-level grade filter (or "all A-grade") without
   first selecting a competition, matching CricketStatz's flat grade pick.
4. **Report discoverability** (task 2 long tail) — search/favourites/recent on the Report Catalogue (already in
   the universal-filter proposal, Deliverable C §4-equivalent). Keeps breadth without the ~230-item scroll.
5. **Keep leading on safety and honesty** — the approval/audit/known-minimum model is a genuine advantage;
   surface it (e.g. a small "verified vs known-minimum" legend on reports) rather than hiding it.

## Net
OneStats is already simpler than CricketStatz for the everyday volunteer tasks and safer for data entry, while
matching it on opposition filtering, data-quality and partnerships (several closed during this audit). The
biggest remaining usability wins are **Player Compare** and **report discoverability** — features that move
OneStats ahead of the benchmark rather than just to parity.
