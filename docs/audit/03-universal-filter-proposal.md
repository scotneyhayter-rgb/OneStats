# Audit Deliverable C — OneStats Universal Statistical Filter (Proposal)

**Stages 2–3. A proposal for approval — nothing here is built yet (Part 14 Stage 7 gate).** Designs one
consistent Basic/Advanced filter experience used across reports, profiles, dashboards, comparisons and
Ask OneStats, driven by the one engine so every surface returns identical numbers.

## 1. Where OneStats stands today
`engine._where` (and the catalogue `filters`) support: **season, grade, competition, team, club
(organisation), home/away, format, date range, finals/grand-final split**. UI exposes roughly the same.
Architecture is already "one engine + filters", so this is an **extension, not a rebuild**.

## 2. CricketStatz filter model (benchmark, captured live)
season · date range · grade (**multi**) · match type · pool · finals · match result · toss · innings · round ·
club · **opposition club** · team · **opposition team** · **ground** · exclude-ground · **country** · player ·
**fielder** · **bowler** · official · **batting position** · fall-of-wicket position · captains/keepers flags ·
active-only · **min/max thresholds** (matches, innings, runs, wickets, overs, catches, stumpings, balls, age) ·
result limit. One form, every report.

## 3. Gap analysis → what to add (ranked)

| Gap | Why it matters | Effort |
|---|---|---|
| **Opposition (club/team)** | The headline gap. "vs Pomonal" is impossible today; head-to-head needs it | Med — add opposition to contributions/filter (the bowling team / opponent is derivable per contribution) |
| **User-adjustable qualification (min/max)** | Averages reports hardcode min_runs/min_wickets; users can't set "min 10 innings" | Low — surface existing `min_*` as filter inputs |
| **Specific venue/ground** (not just home/away) | Ground records | Low–Med — needs venue on contribution or match join |
| **Multiple grades + multiple seasons / season range** | "A Grade, 2000–2025" | Low — accept lists; `IN (...)`; date-range already exists |
| **Match type / format exposed consistently** | T20 vs one-day vs multi-day splits | Low — `format` already in engine; expose everywhere |
| **Innings (1st/2nd), toss, batting position** | Conditional cuts | Med — need these on the contribution or a match join |
| **Country** | For future Test/FC/ODI/T20 workspaces (Part 18) | Low design now, data later |
| **Player-as-fielder / player-as-bowler filters** | "dismissals by fielder X off bowler Y" (have fielder-bowler combos report) | Med |

## 4. Proposed Universal Filter Bar

**Always-visible (Basic), only those valid for the current report/data:**
`Season ▾ | Competition ▾ | Grade ▾ | Team ▾ | Opposition ▾ | Match Type ▾ | Venue ▾ | ⚙ More filters`

**Advanced (progressive disclosure under "More filters"):**
multi-season / season range · custom date range · multiple grades · opposition exclude · specific ground ·
finals / grand-final · innings · toss · batting position · min/max qualification (matches/innings/runs/
wickets/overs/catches/stumpings) · result limit · sort override.

### Rules
- **Only show filters the report and its data support** (don't offer venue on a fielding leaderboard that
  ignores it; don't offer batting position on a team report).
- **Qualification applies to the *filtered* population** — "min 10 innings" means 10 innings *within* the
  current filter, computed before ranking (OneStats already filters pre-aggregation; keep that contract).
- **Include/AND across dimensions; multi-value = OR within a dimension; explicit exclude** (opposition, ground).
- **Active filters always visible as removable chips**, and written into report headings, CSV, PDF, saved
  configs and published metadata — a filtered report must never read as all-time.
- **One result everywhere**: tables, profiles, dashboards, Ask OneStats, CSV, PDF, published snapshots share
  this filter object and the one engine — no parallel filtering code.

### Saved presets
Personal + workspace-approved shared presets (name, edit, duplicate, delete, reset). Examples: *RMCC All-Time*,
*A Grade Only*, *Finals*, *Grand Finals*, *vs Pomonal*, *Last 5 Seasons*, *International Test Cricket*.
Respect workspace permissions; presets are filter definitions only (no private DB exposure).

### Basic vs Advanced
Basic = clean, plain-language, few controls → meaningful report in one or two choices (volunteers).
Advanced = the full set via progressive disclosure (statisticians). Same filter object underneath.

## 5. Acceptance test (the user's own example)
> Highest batting averages, RMCC, 2000/01–2025/26, A Grade, **vs Pomonal**, home-and-away only, **min 10 innings**, sorted by average.

Must be expressible and return the same number on the report, the player profile and Ask OneStats. Today it
**fails** on opposition and user-set min-innings — the two highest-priority additions. This query becomes the
regression fixture when the filter ships.

## 6. Extensibility (Part 18)
The filter object must carry **country / team-type** and a **format family** (Test / First-Class / One-Day /
T20) so the same bar serves future international and format-specific workspaces without a redesign — add the
fields now (inert where unused), populate when those workspaces exist. Never fabricate format/country for
existing grassroots data.

## 7. Implementation sketch (for the approved stage, not now)
1. Add opposition + venue(+ground) + innings/toss/batpos to `match_stat_contribution` (or a match join in
   `_where`) so the filter resolves without per-report SQL. Backfill via `recalc.backfill` (idempotent).
2. Extend `engine._where` to accept lists (seasons, grades) and `opposition_*`, `ground_id`, `innings`,
   `min_*`/`max_*` passthroughs.
3. One `FilterBar` React component (Basic/Advanced, chips) bound to a single `filters` object; reused by
   reports, profiles, dashboards, compare, Ask OneStats.
4. Presets table (workspace-scoped, RLS) + personal presets.
5. Filter labels into report headers/CSV/PDF/publish metadata.
6. Fixtures: the §5 query + per-dimension unit tests (filter applies pre-aggregation; qualification on the
   filtered set).

**Decision needed:** approve this direction and priority order (opposition + adjustable qualification first),
then it moves to Stage 7 implementation in tested increments.
