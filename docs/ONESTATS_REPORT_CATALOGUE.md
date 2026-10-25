# OneStats — Report Catalogue & Cricket Statz Comparison

Deliverable for the complete Report Catalogue (Phase 12 expansion), 2026-10-26. Companion to the
requirements matrix ([ONESTATS_RMCC_REPORT_MATRIX.md](ONESTATS_RMCC_REPORT_MATRIX.md)).

## 1. Current OneStats report inventory

**79 distinct reports**, all over the one deterministic engine (scope is a filter, not a separate report):

| Category | Reports |
|---|---|
| Batting | 18 |
| Bowling | 11 |
| Fielding | 4 |
| Wicketkeeping | 4 |
| Captaincy | 11 |
| Partnerships | 6 |
| Player Participation | 5 |
| Teams | 7 |
| Seasons | 1 |
| Finals & Grand Finals | 4 |
| Historical Records | 5 |
| Awards & Achievements | 2 |
| Data Integrity & Audit | 1 |
| **Total** | **79** |

**Update 2026-10-26:** the six previously-outstanding reports are complete (consecutive matches — player &
captain, consecutive scores without a duck, wicketkeeping dismissals in an innings, captaincy comparison,
captaincy by season), the best-bowling-in-a-match **runs tie-break** is corrected, the **approved forfeit
policy** is applied throughout, and **Captain2 is excluded by user decision**. See the matrix for per-report
status.

Each report has a name, description, category, available filters, qualification rules, completeness
limitations, a working **View Report** action, **PDF** export (branded, print-ready) and **CSV** export for
tabular reports. A **printable catalogue index** lists them all. The full per-report status (implemented /
tested / partial / outstanding) is in the requirements matrix.

Delivered via: `GET /stats/catalogue` (metadata), `GET /stats/reports/{id}` (data),
`GET /stats/reports/{id}/pdf`, `GET /stats/reports/{id}/csv`, `GET /stats/catalogue/index.pdf`; UI at
**Statistics → Report Catalogue** (`/statistics/catalogue`) with search, category browse, favourites,
recently-used, inline viewer with the Home&Away/Finals/Grand-Final split, and PDF/CSV export. Saved custom
report configurations (Report Builder, §27) persist in the database across restarts.

## 2. Cricket Statz comparison (documented, honest)

Cricket Statz's public materials do **not** substantiate a "260+ reports" figure. What the sources say:

- A SourceForge listing describes **"over 120 statistics reports."**
- A Cricket Leinster article (older) describes **"77 reports in total"**, reports filterable by club,
  ground, date and competition, and **CSV export**.
- The vendor's own getting-started page names only a handful of reports explicitly (Match Draw, Competition
  Points ladder, Match Results, Result Summary by Round) and otherwise says "various statistics reports".
- A support-forum post confirms Cricket Statz does **not** do 3-way partnerships — it splits a partnership
  by the two batters who actually batted together.

**Conclusion:** no authoritative complete list of Cricket Statz reports is publicly available, and the
"260+" benchmark could **not** be independently verified; published figures are **77–120+**. OneStats does
**not** claim numerical parity. OneStats' 73 reports cover the same functional breadth the sources attest
(batting, bowling, fielding, partnerships, ladders, player/season records, filtering, CSV) and add
specialist reports (D12 bowling combinations for 2/3/4 bowlers — beyond CS's two-batter partnership model;
streak/consecutive records; data-integrity reconciliation).

Feature-by-feature (from documented CS capabilities):

| Capability | Cricket Statz (documented) | OneStats |
|---|---|---|
| Batting/bowling/fielding leaderboards | Yes | Yes (metric-by-metric) |
| Partnerships | 2-batter only | 2-batter + per-wicket + pair aggregates |
| Bowling combinations | Not documented | 2/3/4-bowler D12 combinations |
| Ladders / competition points | Yes | Yes (configured scheme, historical rules) |
| Seasonal / annual leaders | Yes | Yes |
| Streak / consecutive records | Not documented | Team + captaincy streaks |
| Filtering (club/ground/date/comp) | Yes | Yes (season/grade/comp/team/date/format/venue/finals) |
| CSV export | Yes | Yes |
| PDF export (branded) | Not documented | Yes |
| Data-integrity reconciliation | Not documented | Yes |

Sources: [cricketstatz.com](https://cricketstatz.com/), [getting-started](https://www.cricketstatz.com/getting-started),
[SourceForge listing](https://sourceforge.net/software/product/Cricket-Statz/),
[Cricket Leinster](https://cricketleinster.ie/news/launch-of-cricket-leinster-data-centre),
[CS support forum (partnerships)](https://www.cricketstatz.com/support-forum/questions/partnerships-reports-retired-batters).

## 3. Missing / outstanding reports

**None outstanding.** The six RMCC requirements previously flagged are now implemented and tested, and the
best-bowling runs tie-break is corrected (see the matrix). Remaining items are genuine *limitations* (not
missing reports): undocumented-fixture gaps in streaks (flagged known-minimum), career-economy single
over-length, and the rare second-keeper-in-an-innings split.

## 4. Implemented improvements (this expansion)

- A dedicated, categorised **Report Catalogue** section (search, favourites, recently-used, inline viewer).
- **CSV export** and a **printable catalogue index** PDF.
- New calculations over the one engine: **streaks** (`streaks.py`), **single-season / innings / match /
  pair records** (`records_detail.py`), and a `boundaries` metric.
- RMCC qualification defaults wired in (batting avg min 500, SR min 100, bowling min 50 wickets, captaincy
  min 20 eligible) and configurable per request.

## 5. Number of genuinely distinct working reports

**79** — counted by distinct metric/structure. Scope filters (season, grade, competition, team, date,
venue, finals split) are **not** counted as separate reports. The finals/grand-final entries that preset a
split are labelled as such and counted once each. (The Captaincy Comparison is an interactive tool rather
than a flat table, included in the count once.)

## 6. Reports dependent on data that may be unavailable

Boundaries counts, strike/economy rates, fielder/bowler attributions and partnership construction depend on
the scorecard recording those fields. Where unrecorded, totals are a **known-minimum** (never zero) and the
report flags it. Career economy assumes a single over length.

## 7. Test results

- `tests/test_report_catalogue.py`: **every** one of the 79 entries opens and exports CSV; the catalogue
  index renders; new calculations verified against hand-computed values (streaks = 4, highest innings =
  120, 90s/40s = 1, best single season = 260, ducks inflicted = 4, fielder–bowler = 4, most expensive = 60,
  boundaries = 20, grand-final split = 30; consecutive matches = 4, consecutive captained = 4, without-duck
  = 4, best bowling in a match = 5/60, captaincy-by-season and comparison; WK dismissals in an innings = 3).
- `tests/test_forfeit_policy.py`: the six forfeit cases (full no-play forfeit → team result + points but no
  appearance/captaincy; partly-played → preserved; normal-match control).
- Existing `test_reports_catalogue.py` / `test_reports_pdf.py` / engine / partnership / recalc suites: green.
- Desktop `report-catalogue.test.tsx`: the catalogue lists, searches and opens a report.

## 8. Updated acceptance checklist

The combined Phase 11–13 programme ([60-combined-acceptance-phase11-13.md](60-combined-acceptance-phase11-13.md))
gains a **Report Catalogue** test section.
