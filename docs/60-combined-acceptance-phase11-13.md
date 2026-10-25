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

## Workflow

Run each test, record Pass/Fail/Blocked and any defect reference. Fix defects found, rerun affected
regression tests, then produce the final combined acceptance report. **Phase 14 does not begin until the
user formally accepts this combined programme.** A genuinely unavailable OneVault API may remain a
documented external dependency under conditional acceptance if all independently testable functionality
is satisfactory and the user approves.
