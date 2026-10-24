# CricketStatz JSON Export — Format Analysis (Phase 6, Stage 8)

Source of truth for the genuine CricketStatz export used by the Stage 8 importer. Derived by
read-only inspection of a real export; the original file is never modified, moved or committed.

- **Analysed file:** `CS26266_1br2is1nqhk.json` (~8.3 MB), located in the user's Downloads.
- **Encoding:** UTF-8 (tolerate a BOM — read with `utf-8-sig`).
- **Shape:** a single JSON **object** whose values are the collections below.

## Top-level collections (actual counts in the analysed export)

| Key | Count | Notes |
|---|---|---|
| `clubs` | 46 | `ClubID`, `Name` |
| `teams` | 56 | `TeamID`, `Name`, `ClubID` |
| `venues` | 43 | `GroundID`, `Name` (`"?"` = unknown) |
| `divisions` | 7 | `GradeID`, `Name` (grades) |
| `players` | 3595 | `PlayerID`, `Firstname`, `Lastname`, `DOB`, `ExternalID`, `MyClub`, `Battingtype`, `Bowlingtype`, `isActive` |
| `officials` | 13 | same shape as players (subset of fields) |
| `matches` | 940 | fixture header — see below |
| `innings` | 940 wrappers → **2249** innings | nested under `cricket_Innings` |
| `batting` | 940 wrappers → **30832** rows | nested `cricket_batting` |
| `bowling` | 940 wrappers → **15629** rows | nested `cricket_bowling` |
| `ballByBall` | 940 wrappers | `cricket_overs` — **effectively empty** in this export |
| `retirements` | 3 wrappers | `cricket_retirements` |
| `awards`, `history` | `null` | not present |

No explicit export-format/version field is present in the file.

### Counts vs the reference totals

Matches (940), batting rows (30832), players (3595), officials (13), venues (43), divisions (7),
teams (56), clubs (46) **match exactly**. Innings is 2249 vs the reference 2248 (+1) and bowling
rows 15629 vs 15588 (+41) — small positive differences consistent with this export being taken a
little later than the reference snapshot. To be confirmed against the user's expectation; nothing
is dropped or invented either way.

## `matches` row

`MatchID`, `HomeTeam`, `AwayTeam`, `DatePlayed` (ISO, may be `...T00:00:00`), `Ground`, `Grade`,
`Result` (code), `pool`, `round` (verbatim — **never** classifies the match), `comment`,
`matchtype` (1/2/3), `homebpoints`, `awaybpoints`, `homecaptain1`, `homekeeper1`, `homekeeper2`,
`awaycaptain1`, `awaykeeper1`, `awaykeeper2`, `tosswonby`, `official1..3`, `scorer1..3`.

Person references (captains/keepers/officials/scorers/toss) are **PlayerID**s; `0` = none/unknown.
Coverage in this export: a captain in 765/940, toss in 359/940, an official in 46/940 — partial
historical data; unknowns stay unknown.

## Nested scorecard body (per match, under `cricket_Innings`)

- **innings**: `InningsID`, `InnsNumber`, `battingteam`, `bowlingteam`, `iresult`, `Byes`,
  `Legbyes`, `Noballs`, `Wides` (extras are at **innings** level).
- **batting** (`cricket_batting`): `Batpos`, `BatsmanID`, `Howout` (dismissal code), `Fielder`,
  `Bowler`, `Score`, `Balls`, `mins`, `sixes`, `fours`, `mvp`, and the **fall of wicket embedded
  per batter**: `FOW` (team score at fall), `FOWPos` (wicket number), `FOWOvers`, `FOWBatID`.
- **bowling** (`cricket_bowling`): `bowlerID`, `Maidens`, `Overs` (cricket notation), `Wickets`,
  `RunsA` (runs conceded), `wides`, `noballs`.
- **retirements** (`cricket_retirements`): `RetiringBatsmanID`, `RetiredAtFOW`, `RetiredAtRuns`,
  `ReturnedAtFOW`, `ReturnedAtRuns`.

Edge cases seen: one empty batting row (`{}`) and one `Howout` of `null` — parse defensively,
flag, never crash. All `BatsmanID`s resolve to the `players`/`officials` list (clean provenance).

### `Howout` dismissal codes — observed distribution (semantics TO BE CONFIRMED)

`{0: 10312, 1: 3089, 2: 6166, 3: 7645, 4: 594, 5: 26, 6: 1335, 7: 909, 8: 494, 9: 17, 10: 1,
20: 63, 22: 178, 23: 1, 24: 1, null: 1}`

The code→dismissal-type mapping is **not inferred** here. Stage 8b maps only evidence-confirmed
codes and leaves the rest **unresolved** for administrator review (never guessed), consistent with
the existing importer's treatment of ambiguous grades and result codes.

## Importer compatibility

- **Structural** (`clubs`/`teams`/`venues`/`divisions`/`matches`): the genuine JSON is already in
  the exact payload shape `imports.parse_and_stage` consumes — it parses, validates and previews
  with **no importer changes** (proven in a rolled-back transaction: 46/43/7/56/940 staged,
  940 matches promotable, 4 ambiguous grades unresolved).
- **People** (`players`/`officials`): handled by the existing `people_import` (sentinel-aware:
  `DOB 1700-01-01` → unknown, `MyClub`/`ClubID 0` → unknown).
- **Scorecards** (`innings`/`batting`/`bowling`/FOW/extras/retirements): **new** — Stage 8b adds a
  thin JSON adapter that flattens `cricket_Innings` into stageable records and promotes them into
  the existing innings/batting/bowling/FOW/partnership models, with player links resolved via the
  people importer. The common staging/idempotency/rollback/audit engine is reused unchanged.
