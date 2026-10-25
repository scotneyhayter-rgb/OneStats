# Combined Manual Acceptance Programme — Phases 11, 12 & 13

Per the user's instruction, manual acceptance for **Phase 11 (Media Archive)**, **Phase 12 (Statistics
& Reporting)** and **Phase 13 (Records, Rankings & Achievements)** is conducted together, after Phase 13.
None of these phases is recorded as formally user-accepted until the user completes this programme.

Run in the **OneStats Sandbox** with synthetic records (protect production/historical data). Record each
test **Pass / Fail / Blocked**, with a defect reference where relevant. A blocked external integration
(e.g. OneVault with no verified API) is **not** an application defect — record it as Blocked and keep it
distinct.

## Prerequisites & recommended order

1. Start the backend + desktop app. Sign in as Super Admin (holds every permission).
2. Seed synthetic data: create an organisation, a competition + season + grade, two teams, several
   players, and enter/approve a few scorecards (include a match with unknown balls/runs, a run out, a
   stumping, captains, a grand final, and a tie) so statistics and records have something to show.
3. Recommended order: **Phase 12 (statistics)** first (records/badges depend on approved stats), then
   **Phase 13 (records)**, then **Phase 11 (media)** which is independent.

Full test data notes and expected results are summarised below; the engine is approved-data-only, so
only **approved** scorecards appear in statistics/records (draft/disputed are excluded).

---

## Phase 11 — Media Archive & OneVault (20 tests)

Use the detailed checklist in [57](57-phase11-acceptance.md). Summary of coverage (Club Management →
Media Archive): 1 Library navigation · 2 original-quality upload · 3 multiple-file upload · 4 duplicate
detection · 5 metadata management · 6 copyright/privacy controls · 7 image viewing · 8 PDF viewing ·
9 thumbnail generation · 10 link media to matches · 11 link media to players · 12 Research Centre
integration (promote a source) · 13 Club Heritage Collection · 14 external file references · 15 stable
media identifiers · 16 storage migration · 17 checksum verification (Storage & Integrity → Verify
archive) · 18 backup/restoration (manifest) · 19 workspace isolation · 20 **OneVault capability
detection** — must show **unavailable** (do not mark a simulated adapter as a verified live integration).

---

## Phase 12 — Statistics & Reporting (28 tests)

Section: **Statistics** (left sidebar). Each report is one engine; the PDF matches the on-screen table.

| # | Test | Where / How | Expected |
|---|---|---|---|
| 1 | Batting statistics | Statistics → Batting | Runs, HS, Avg (runs÷dismissals), SR, 50s/100s/ducks correct for approved data |
| 2 | Bowling statistics | Statistics → Bowling | Wkts, Avg, Econ (configured over length), SR, 5wi correct |
| 3 | Fielding statistics | Statistics → Fielding & WK | Catches incl. keeper catches; run outs separate |
| 4 | Wicketkeeping | Statistics → Fielding & WK | Keeper catches + stumpings counted as WK dismissals, not double-counted |
| 5 | Run-out reconciliation | API `/stats/matches/{id}/reconciliation` or a match's integrity | Recorded wkts vs dismissals; run outs shown; warning if incomplete |
| 6 | Captaincy | Statistics → Captaincy | Credited captain, Win % over eligible (excl. no-results), GF columns |
| 7 | Batting partnerships | API `/stats/partnerships/batting` | Highest + per-wicket from approved data |
| 8 | Bowling partnerships (D12) | API `/stats/partnerships/bowling-groups?size=2` | Combined wickets in matches all members played; run outs excluded |
| 9 | Career aggregates | Statistics (no season filter) | Totals across all approved matches |
| 10 | Seasonal aggregates | Statistics → filter a season | Only that season's matches |
| 11 | Home & Away / Finals / GF split | Statistics → Matches filter | Split changes the figures correctly; "All" combines |
| 12 | Competition points | API `/stats/ladder?competition_id=…` | Ladder uses the configured scheme; bonus/penalty applied |
| 13 | Playing conditions | Set a points scheme on a competition | Ladder reflects the configured scheme, not the default |
| 14 | Historical over lengths | Bowling with `over_length` param | Economy uses the configured over length, not assumed 6 |
| 15 | Unknown vs zero | A player with unknown balls | SR blank (not 0); "known min." noted |
| 16 | Known-minimum values | Statistics note / integrity | Unknown-data totals flagged, not confirmed |
| 17 | Qualification thresholds | Batting → Min runs (e.g. 500) | `qualified` flag applies; unqualified kept, not deleted |
| 18 | Approved-only statistics | Create a draft match | It does **not** appear in any statistic |
| 19 | Report filtering | Apply competition/split/venue | Table updates consistently |
| 20 | Report Builder | Statistics → Save / open a saved report | Save a report config; reopen it (applies filters); shared vs private; owner-only delete |
| 21 | On-screen readability | Any report | Right-aligned numerics, fixed decimals, sticky header, sortable |
| 22 | Portrait PDF export | Batting → Export PDF | A4 portrait, logo/title/date, Page X of Y |
| 23 | Landscape PDF export | A wide report → Export PDF | Auto-landscape; no clipped columns |
| 24 | Multi-page PDF pagination | A long report → Export PDF | Table header repeats each page; no split rows where avoidable |
| 25 | Workspace branding in PDF | Export with a workspace logo set | Logo + club name in the header |
| 26 | On-screen/PDF consistency | Compare table vs PDF | Same figures (one engine) |
| 27 | Recalculation after correction | Edit + re-approve a scorecard | Stats update; never doubled |
| 28 | Large report performance | Many players | Loads responsively; pagination/virtualised scroll |

**Visually inspect** a representative portrait and landscape PDF — successful generation does not prove
professional formatting.

---

## Phase 13 — Records, Rankings & Achievements (22 tests)

Section: **Records & Achievements** (Club Management → Records & Achievements).

| # | Test | Where / How | Expected |
|---|---|---|---|
| 1 | All-time record holders | Records → All-time | Prominent No.1 + value; expand for ranking |
| 2 | Seasonal leaders | Records → Seasonal leaders | Leading run scorer + wicket taker per season; seasons not combined |
| 3 | Career milestones | API `/records/milestones/{person}` | Thresholds with states (confirmed/known-min/upcoming/indeterminate) |
| 4 | Achievement badges | API `/records/badges/{person}` | Calculated badges with state; separate from awarded honours |
| 5 | Player profile achievements | Player profile | Milestones/badges shown (profile integration) |
| 6 | Life Member recognition | Records → Life Members; add via `/records/honours` | Recorded + authorised; shown; never inferred |
| 7 | Honorary Member recognition | As above | Distinguished from Life Member and from calculated badges |
| 8 | Batting partnership records | Records / book | Highest partnership shown with supporting match |
| 9 | Bowling group records | API (D12) | 2/3/4-player groups ranked by combined wickets |
| 10 | Captaincy records | Records / Statistics → Captaincy | Most captained/wins/Win %; GF columns |
| 11 | Team records | Statistics → Teams | Wins/losses/draws/ties; Win % |
| 12 | Grand Final records | Records with split = Grand Finals | GF-only figures |
| 13 | Historical provenance | A record from historical data | Approved-only; known-minimum flagged; drill-down to match |
| 14 | Upcoming milestones | Records → Upcoming | From **confirmed** totals only (not incomplete) |
| 15 | Record recalculation | Correct + re-approve a scorecard | Records update; idempotent; no duplicate awards |
| 16 | Tied records | Two players with equal top value | Both shown as tied; tie not broken arbitrarily |
| 17 | Record qualification thresholds | Avg/SR records with min qualification | Unqualified separated, not hidden |
| 18 | Records dashboard | Records page | Featured holders, seasonal leaders, upcoming, honours — real data |
| 19 | Club Record Book | Records → Club Record Book (PDF) | Multi-section book with cover page + page numbers |
| 20 | Record Book PDF export | As above | Professional, branded; known-minimum note where applicable |
| 21 | Workspace permissions | Recording an honour | Requires `honour.manage`; viewing requires `match.view` |
| 22 | Privacy & publication eligibility | Media on a record | Junior/private media not exposed; publication stays explicit |

---

## Phase 13 (continued) — Player Profiles (16 tests)

Open from **People** (left sidebar) → open a person → **View full career profile →** (route
`/people/<id>`). Profiles compose the one engine; nothing is fabricated; unknown is never shown as zero.

| # | Test | Where / How | Expected |
|---|---|---|---|
| P1 | Profile appearance | Open a player's full profile | Professional header (avatar, name, role, badges), clean cards, light/dark |
| P2 | Navigation | Click the tabs | Overview/Batting/Bowling/Fielding&WK/Captaincy/Seasons/Matches/Records&Milestones/Awards&Honours/Media switch without reload; "Directory" returns |
| P3 | Career statistics | Overview + discipline tabs | Matches/runs/avg/wickets etc. match the Statistics section (one engine) |
| P4 | Adaptive cards | A batting-only player | No misleading zero-wickets card; batting prominent |
| P5 | Season-by-season | Seasons tab | One row per season; seasons not combined; expandable figures |
| P6 | Match history | Matches tab | Match-by-match line; opens match; missing figures blank (not 0) |
| P7 | Records & milestones | Records & Milestones tab | Records held + milestone states (reached / known-minimum / to-go) |
| P8 | Achievement badges | Overview | Calculated badges with state; distinct from awarded honours |
| P9 | Awards & Honours | Awards & Honours tab; add via `/records/honours` | Custom categories (Best & Fairest, …); recorded not inferred |
| P10 | Life Membership | A Life Member | Life Member badge in the header; shown in Awards |
| P11 | Photographs | Media tab | Thumbnails of the player's photos; placeholder when none; privacy respected |
| P12 | Multi-club career | A player in >1 club | Clubs listed; **one** identity (no duplicate profiles) |
| P13 | Unknown handling | A player with unknown figures | Known-minimum "min." indicators; never shown as zero |
| P14 | Profile PDF export | Profile → Export PDF | A4, branding, cover page, career tables — same figures as screen |
| P15 | Graphical career charts | Seasons tab (player with >1 season) | Runs/season, batting avg/season, wickets/season, cumulative runs render as clean SVG charts; unknown is a gap, not zero; accessible labels |
| P16 | Grand Finals section | Grand Finals tab | GFs played, premierships (team won — recorded, never inferred), GF batting/bowling/captaincy, list of every GF; header shows premiership badge; "No grand finals recorded" when none |

---

## Phase 12 (continued) — Report Catalogue (15 tests)

Open from **Statistics → Report Catalogue** (`/statistics/catalogue`). 79 reports over the one engine; see
[ONESTATS_RMCC_REPORT_MATRIX.md](ONESTATS_RMCC_REPORT_MATRIX.md) for every report's status.

| # | Test | Where / How | Expected |
|---|---|---|---|
| RC1 | Catalogue loads | Open Report Catalogue | Categorised, searchable list; report count shown |
| RC2 | Search | Type part of a report name | List filters by name/description/category |
| RC3 | Browse by category | Click a category chip | Only that category's reports shown |
| RC4 | Open a report | View report on any entry | A working table opens (columns + rows), no dead links |
| RC5 | Favourites | Star a report | It appears under ★ Favourites; persists after restart |
| RC6 | Recently used | Open a few reports | They appear under Recently used; persists after restart |
| RC7 | Split filter | In the viewer, choose Grand Finals | Figures restrict to grand finals (same engine) |
| RC8 | PDF export | Export PDF from a report | Branded A4 PDF, same figures as screen |
| RC9 | CSV export | Export CSV from a tabular report | CSV with the same columns/figures |
| RC10 | Printable index | Printable index button | A PDF listing every report by category |
| RC11 | Streak & record reports | Open team/captaincy streaks, single-season, highest innings | Correct consecutive/record values; known-minimum flagged where data is incomplete |
| RC12 | Qualification & empty states | Open an averages report and a report with no data | Qualified players only (configurable threshold); clean empty state, never a crash |
| RC13 | Captaincy Comparison | Captaincy → Captaincy Comparison; pick 2+ captains | Side-by-side table (matches, W/L/D/T, win %, consecutive wins, finals/GF); leading value highlighted |
| RC14 | New reports open | Open consecutive-matches (player & captain), without-a-duck, WK-in-an-innings, best-bowling-in-a-match, captaincy-by-season | Correct values; best bowling ranks by wickets then fewest runs; known-minimum flagged where incomplete |
| RC15 | Forfeit policy | A full forfeit with no play; a partly-played awarded match | Team gets the result/points; a no-play forfeit adds **no** player appearance or captaincy; a partly-played match keeps verified participation |

**Visually inspect** a representative report PDF and the catalogue index.

## Pre-acceptance audit spot-checks (added 2026-10-26)

The full system audit ([ONESTATS_FULL_SYSTEM_AUDIT.md](ONESTATS_FULL_SYSTEM_AUDIT.md)) fixed four
defects before this programme. Add these quick confirmations:

| # | Check | Expected |
|---|---|---|
| A1 | A bowler whose matches used **eight-ball overs** → view Bowling economy | Economy uses the configured over length (not a fixed six) |
| A2 | Open a **captain's** profile → Captaincy tab | Captaincy figures are populated (previously blank) |
| A3 | Export a **player-profile PDF** | A4 **portrait**, cover shows the club name once (no duplication) |
| A4 | A bowler with matches in **different over-length** competitions (6-ball and 8-ball) → view career Economy | Economy uses each match's real over length (true overs summed), not one assumed value; flagged when a match's over length is unrecorded |
| A5 | An innings with **two wicketkeepers** → Fielding & WK + "WK dismissals in an innings" | Each keeper is credited only with their own catches/stumpings; an unknown-keeper dismissal is not attributed to anyone |

## Workflow

Run each test, record Pass/Fail/Blocked and any defect reference. Fix defects found, rerun affected
regression tests, then produce the final combined acceptance report. **Phase 14 does not begin until the
user formally accepts this combined programme.** A genuinely unavailable OneVault API may remain a
documented external dependency under conditional acceptance if all independently testable functionality
is satisfactory and the user approves.
