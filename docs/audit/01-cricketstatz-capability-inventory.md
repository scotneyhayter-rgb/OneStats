# Audit Deliverable A — CricketStatz Capability Inventory

**Stage 1 (Discovery). Captured 2026-11-01 from the live CricketStatz account (RMCC, club 26267),
read-only, with the user's authorisation.** Direct observation unless marked *inferred*. No CricketStatz
source code, markup or styling was copied; only the numeric/behavioural facts an authorised user can see.

## 1. What CricketStatz actually is (structural facts)

- **A hosted web service** (`www2.cricketstatz.com`), not desktop software. The data lives on CricketStatz
  servers; the user's "export" (the `CS26266_*.json` we imported into OneStats) is a server-produced feed.
- **Every report is machine-readable JSON** at `GET /ss/rrj?mode=<id>&club=<id>&<filters>` (the on-page
  "json" link next to each rendered report). The HTML report page is `/ss/runreport2?...`.
  - Quirk observed: passing `howout=-1` zeroes the run-out column — omit it. `season=00` = the *current*
    season, empty `season=` = all-time. `ech=1` excludes imported career-history summaries.
- **One universal filter form drives all ~230 reports.** The same control set is posted with every `mode`.
  This is the single most important design lesson for OneStats Part 3 (see Deliverable B).
- Fielding attribution (run-out/catch fielder) is tracked **per dismissal, per match** on the batting card
  (confirmed by the "Fielder empty on batting scorecard" report returning per-dismissal rows). It is NOT a
  separate summary — so a fresh export carries it (this underpins the fielder-refresh backfill, commit f0b3bff).

## 2. Universal filter model (every report)

Captured from the report form. Dimensions CricketStatz actually supports, with the field name:

| Group | Fields |
|---|---|
| Time | `season` (single; 00=current, blank=all), `sd`/`ed` (date range) |
| Competition | `grade` (**multi-select**), `mtype` (match type), `pool`, `finals`, `mr` (match result), `toss`, `inns` (which innings), `round` |
| Teams | `club`, `oppclub`, `team`, `oppteam`, `ground`, `xground` (exclude ground), `country` |
| Players | `playerid`, `fielderid`, `bowlerid`, `officialid`, `batpos` (batting position), `fowpos`, `captains`/`keepers` (include flags), `active` (active only) |
| Thresholds | `minmatches`, `mininns`, `minruns`, `maxruns`, `minwickets`, `minovers`, `mincatches`, `minstumpings`, `minballsf`/`maxballsf`, `agemin`/`agemax`, `prmin`/`prmax` |
| Ranking/output | `limit`, free-text `filt`; fantasy-points weights `p_run`/`p_wkt`/`p_uwkt`/`p_ct`/`p_st`/`p_ro`/`p_uro` |
| Career history | `ech` (exclude imported summary aggregates) |

Notable: `grade` is multi-select; most other dimensions are single-select; `xground`/exclude is a dedicated
field, not a general include/exclude per dimension. No evidence of saved filter presets or multi-season
selection (season is single-value) — **opportunities for OneStats to exceed CricketStatz** (Deliverable C).

## 3. Full report catalogue (mode id → name)

~230 reports (CricketStatz markets "260+"; the live list enumerated is below). Grouped by observed section.

### Matches & results
1 Competition Points (NRR) · 208 Competition Points Extended (RpWr) · 2 Match Draw · 12 Match Results ·
189 Match Results Extended · 123 Match Results with Inns Breakdown · 14 Match Round Result Summary ·
105 Recent Results · 27 Highest Innings Totals · 28 Lowest Innings Totals · 214 Shortest All-Out Innings ·
260 Longest Innings · 196 Highest Innings Totals by Opp · 197 Lowest Innings Totals by Opp ·
118 Highest Match Totals by Team · 119 Lowest Match Totals by Team · 182 Highest Match Totals Combined ·
179 Highest Innings Totals without a Century · 185 Lowest All-out Innings Totals with a Century ·
72 Highest Winning Margins by Runs · 73 Narrowest Winning Margins by Runs · 74 Highest Winning Margins by Wkts ·
75 Narrowest Winning Margins by Wkts · 62 Highest Successful Run Chases Final Innings ·
224 Highest Successful Run Chases Extended · 199 Wins with Most Balls to Spare · 200 Wins with Least Balls to Spare ·
265 Win Chance by 1st Innings Total · 94 Tied Matches · 61 Most Extras in an Innings · 165 Extras Top Scoring ·
141 Most Penalty Runs in an Innings · 206 Most Bowlers in an Innings · 42 Match Summary by Opposition ·
82 Match Summary by Total · 111 Most Consecutive Matches Without Loss · 112 Most Consecutive Matches Without Win ·
135 Most Consecutive Toss Wins by Team · 136 Most Consecutive Toss Losses by Team ·
137 Most Consecutive Toss Wins by Captain · 138 Most Consecutive Toss Losses by Captain

### Players (appearances, milestones, lists)
39 Complete Player Summary · 19 MVP Points · 124 Player Points · 21 Most Matches ·
169 Most Consecutive Matches for a Team · 35 Most Wins · 213 Most Grand Final 'Wins' (incl.drawn/tied) ·
142 Highest Win% · 143 Highest Loss% · 45 Longest Serving by Duration · 114 Longest Serving by Season Count ·
116 Players by First Match/Name · 34 Players by First Match/Batting Pos · 266 Players by Last Match/Batting Pos ·
26 Upcoming Match Milestones · 155 Achieved Match Milestones · 240 Match Milestones Over Time ·
84 Matches Played Together · 59 Youngest Players Today · 58 Oldest Players Today · 175 Youngest Players On Debut ·
176 Oldest Players to Play · 121 Oldest Players On Debut · 20 Player List · 122 Players that Have Played ·
53 Match by Match Player Stats · 194 Innings by Innings Player Stats · 178 Player Summary by Team ·
209 Player Summary by Country · 237 Average Age by Season · 255 Did Not Bat/Bowl/Keep Count ·
263 Most Matches Between Appearances · 264 Most Days Between Appearances · 144 Batting Order Optimiser

### Batting
4 Top Run Aggregates · 29 Most Runs in a Season · 247 Most Runs by Season · 6 Top Run Scores ·
254 Most Runs in a Match · 252 Top Run Scores by Position · 110 Top % of Innings Total · 3 Top Batting Averages ·
145 Top Batting Average in a Season · 246 Top Batting Average by Season · 64 Top Batting Strike Rates ·
22 Top Partnerships · 49 Top Partnerships by Wicket · 88 Top Partnership Aggregates ·
203 Most Century Partnerships by Pair · 150 Batting Rankings · 23 Most Boundaries · 171 Most Boundaries in a Season ·
227 Top Boundary Contribution to Runs · 65 Most Sixes · 78 Most Sixes in an Innings · 253 Most Sixes in a Match ·
77 Most Sixes in a Season · 131 Most Fours · 204 Most Fours in an Innings · 205 Most Fours in a Season ·
10 Most 90s · 147 Most 40s · 44 Most Hundreds · 98 Most Hundreds in a Season · 166 Most Hundreds in an Innings ·
81 Most Consecutive Hundreds · 54 Most Fifties · 97 Most Fifties in a Season · 167 Most Fifties in an Innings ·
80 Most Consecutive Fifties · 130 Lowest Century Conversions · 180 Most Innings without a Century ·
181 Most Consecutive Scores without a Century · 32 Most Ducks · 86 Most Golden Ducks · 128 Duck Pairs ·
228 Diamond Ducks · 225 A Century and Duck in Same Match · 76 Most Ducks in an Innings · 87 Most Ducks in a Season ·
79 Most Consecutive Ducks · 85 Most Consecutive Scores Without a Duck · 207 Most Consecutive Runs Before a Dismissal ·
24 Upcoming Batting Milestones · 149 Achieved Batting Milestones · 238 Batting Milestones Over Time ·
232 Youngest to Achieve Runs Milestone · 233 Oldest to Achieve Runs Milestone · 37 Top All-Round Performance ·
226 Opening Batting and Bowling in Same Match · 43 Centurions · 183 Youngest Centurions · 184 Oldest Centurions ·
134 A Century in Each Innings · 51 Top Batting on Debut · 139 Ducks on Debut · 68 Most Balls Faced in an Innings ·
69 Most Balls Faced for a Duck · 93 Most Mins Batted in an Innings · 60 Carrying the Bat ·
71 5-Wicket Batting Collapses · 216/217/218/219 6–9-Wicket Batting Collapses · 70 Batting Howout Frequency Chart ·
89 Innings To Reach Min Runs · 202 Most Participated Runouts (as not out batter) · 91 Unusual Dismissals ·
92 Batters By Howout · 117 Most Outs in an Inns by Howout · 162 Top Team Pair Batting Aggregates ·
223 Top Innings Per Fifty · 256 On This Day - Batting · 258 On This Day - Partnerships · 55 Score by Score

### Bowling
5 Top Wicket Takers · 8 Top Bowling Averages · 146 Top Bowling Average in a Season · 248 Top Bowling Average by Season ·
7 Most Wickets in an Innings · 38 Most Wickets in a Match · 30 Most Wickets in a Season · 249 Most Wickets by Season ·
9 Top Economy Rates · 66 Top Bowling Strike Rates · 151 Bowling Rankings · 36 Most Expensive Bowling in an Innings ·
161 Least Expensive Bowling in an Innings · 127 Most Wides in an Innings · 129 Most No-balls in an Innings ·
148 Most Balls Bowled · 140 Most Balls Bowled in a Match · 158 Most Balls Bowled in an Innings ·
25 Upcoming Bowling Milestones · 152 Achieved Bowling Milestones · 239 Bowling Milestones Over Time ·
235 Youngest to Achieve Wickets Milestones · 236 Oldest to Achieve Wickets Milestones · 261 Youngest 5WI · 262 Oldest 5WI ·
41 Hat Tricks · 48 Most Five Wicket Innings · 11 Most Five Wicket Innings in a Season ·
160 Most Consecutive Innings Taking a Wicket · 83 Most Consecutive Five Wicket Innings · 52 Most Wickets in an Inns on Debut ·
210 Most Wickets in a Match on Debut · 90 Innings To Reach Min Wickets · 159 Top Bowler/Fielder Combos ·
163 Top Team Pair Bowling Aggregates · 168 Top Team Trio Bowling Aggregates · 198 Opening Bowlers by Matches ·
215 Most Ducks Inflicted · 220 Most Golden Ducks Inflicted · 257 On This Day - Bowling

### Wicketkeeping & fielding
13 Top Wicket Keeping · 113 Top Wicket Keeping in an Innings · 31 Top Wicket Keeping in a Season ·
57 Top Wicket Keeping in a Match · 126 Upcoming Keeping Milestones · 157 Achieved Keeping Milestones ·
242 Keeping Milestones Over Time · 33 Top Catches · 56 Top Catches in a Season · 50 Top Catches in a Match ·
63 Top Catches in an Innings · 115 Top Catches in an Innings by Field · 18 Top Catches by Field ·
47 Top Catches by Field in a Season · 99 Top Catches by Field in a Match · 125 Upcoming Catches Milestones ·
156 Achieved Catches Milestones · 241 Catches Milestones Over Time · 133 Most Consecutive Matches Without a Catch ·
102 Top Dismissals · 40 Most Dropped Catches · 46 Top Run Outs · 243 Most Balls Faced To Get Off Mark ·
244 Dismissed First Ball of Innings · 245 Dismissed First Ball of Match

### Over-level
230 Most Runs in an Over · 231 Most Sixes in an Over · 229 Most Balls in an Over · 250 Most Wides in an Over ·
251 Most Noballs in an Over · 268 Most Wickets in an Over

### Officials, lists & awards
67 Umpires and Scorers Match List · 95 Most Matches by Umpires · 96 Most Matches by Scorers ·
103 Club/League Contacts · 104 Stats List · 16 Clubs List · 107 Teams List · 187 Team Awards by Date/Team ·
211 Individual Awards by Date/Player

### Data-quality / integrity reports (CricketStatz's own linting)
132 Incomplete Retirements · 186 Batters Listed Twice · 108 Bowlers/Fielders Not On Batting Card ·
170 Bowlers/Fielders Listed Twice · 109 Players with no data · 153 Captains Not On Team Batting Card ·
154 Keepers Not On Team Batting Card · 164 Bowler catches not listed as C&B · 172 FOWs incomplete vs batting dismissal count ·
174 Captain missing · 173 Keeper missing · 177 Winning margin does not match totals ·
188 MaxOvers not entered for all-out innings · 201 Overs bowled is greater than MaxOvers ·
212 Batting or Bowling scorecard missing · 221 Batter is blank · 222 Bowler is blank · 234 Bowler and Fielder identical ·
267 Abandoned matches with missing players · 270 Bowler empty on batting scorecard · 269 Fielder empty on batting scorecard

## 4. Early observations for the audit (to develop in later deliverables)

- **Data-quality report suite** (section above) is a strong idea OneStats only partly has (the Research
  Centre's gap checks). ~20 "linting" reports catch scorer errors — a MISSING-FUNCTIONALITY candidate.
- **Milestones (upcoming/achieved/over-time)** across batting/bowling/keeping/catches — OneStats has badges
  but not the "upcoming milestones" forward-looking reports.
- **Per-season variants** (…in a Season / …by Season) are pervasive — OneStats should get these via the
  universal filter + a "by season" grouping toggle rather than duplicating each report.
- **One filter form for all reports** validates the Part 3 universal-filter direction; OneStats can exceed it
  with multi-season, saved presets, per-dimension include/exclude, and visible filter chips.

*Not yet done (later stages): OneStats-side report catalogue, report-by-report comparison (Deliverable D),
numeric reconciliation (Deliverable E), universal-filter design (C). See docs/audit/00-roadmap.md.*
