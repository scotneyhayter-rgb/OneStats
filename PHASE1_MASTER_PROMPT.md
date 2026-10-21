# OneStats — Phase 1 Master Planning & Architecture Brief

**Version 4.0 — October 2026.** This is the authoritative specification for OneStats
Phase 1 (Planning & Architecture only). It is the source of truth for the dedicated
OneStats session; do not begin Phase 2 or implement production features until the user
explicitly approves the architecture.

---

## Role

Act as Lead Software Architect, Senior Full-Stack Developer, Cricket Statistics
Specialist, Database Architect, Security Engineer, UX Designer and Technical Project
Manager for OneStats.

## Product

- **Name:** OneStats
- **Tagline:** Cricket Statistics Made Simple
- Part of the broader **One** software family (alongside OneVault and future One apps).
- Must be: professional, reliable, secure, accurate, easy to use, scalable; suitable for
  cricket clubs, associations and international cricket research.
- UX as straightforward as Lovable, with the capabilities of a professional cricket
  statistics system.

**Phase 1 = Planning & Architecture only.** Inspect the environment, create planning
documentation and architectural designs. Do not overwrite or modify unrelated projects
(notably OneVault at `C:\OneVault`).

---

## 1. Project vision

OneStats will provide: cricket organisation management; multiple independent workspaces;
club/association branding; competition & season management; player & official profiles;
scorecard entry; historical match research; automatic online match discovery; third-party
scorecard importing; Cricket Statz data migration; original historical document
preservation; statistical calculations; historical records; comprehensive reporting;
captaincy statistics; player milestones; data integrity auditing; natural-language
statistical queries; mobile records viewing; automatic website statistics publishing;
optional OneVault integration; future integration with other One software.

- **Initial priority workspace:** Rhymney/Moyston Cricket Club (RMCC).
- **Additional initial workspace:** International Cricket.

## 2. Development technology (evaluate)

- **Windows desktop:** Tauri, React, TypeScript, Tailwind CSS, shadcn/ui.
- **Backend:** Python, FastAPI.
- **Database:** PostgreSQL.
- **Also:** background jobs, secure APIs, role-based permissions, database migrations,
  automated backups, logging, automated testing, media storage, mobile-responsive web
  portal, website publishing services.

Inspect the existing OneStats project before recommending changes. Prefer a practical
architecture maintainable by a small team using Claude Code. Do not introduce unnecessary
infrastructure.

## 3. Windows development environment

Confirm availability of: Claude Code, VS Code, Git, Node.js, Python, PostgreSQL, Rust,
Cargo, Microsoft C++ Build Tools, WebView2. Document versions and compatibility concerns.

PostgreSQL must use: a properly secured administrative account; a separate least-privilege
OneStats application role; appropriate database permissions; secure credential storage.
Do **not** use the superuser for normal operations. Do **not** expose the database to the
public internet. Do not repeat installations unnecessarily.

## 4. Application navigation

Six primary sections: **Dashboard, Matches, People, Statistics, Ask OneStats, Settings.**

- **Matches:** Match Management, Scorecard Entry, Import Matches, Research Centre.
- **Statistics:** Overview, Club Records, Player Statistics, Batting, Bowling, Fielding,
  Partnerships, Teams & Captains, Milestones & Achievements, Report Builder, Data
  Integrity.

Clean, consistent navigation; avoid excessive menus and steps.

## 5. Workspaces

Multiple independent workspaces. Initial: (A) Rhymney/Moyston Cricket Club,
(B) International Cricket. Each workspace has separate cricket organisations,
competitions, people, matches, statistics, research, media, users & permissions,
branding, imports, website publishing settings. The Super Administrator manages all
workspaces. Enforce workspace isolation at the server and database access layers.

## 6. Workspace onboarding

Only the Super Administrator can create and onboard a workspace. Guided setup wizard:
(1) organisation details, (2) branding, (3) cricket programs, (4) competitions,
(5) grades, (6) historical affiliations, (7) initial data import, (8) users &
permissions, (9) review & activation. Support save/resume, optional steps, and templates
for clubs, associations and international cricket.

## 7. Workspace branding

Up to four official colours (primary, secondary, third, fourth) plus a separate accent
colour; light/dark themes; background settings; automatic readable text contrast; logo
upload; alternative logos; organisation name; short name; optional tagline; HEX entry;
visual colour picker; suggested colours extracted from logos; live theme preview; theme
presets; reset to default. Branding applies to the Windows desktop app, mobile portal,
reports, PDF exports and website publishing data. Only authorised users may change it.

## 8. Cricket organisations

Support clubs, associations, international teams, historical clubs, historical names,
historical affiliations, teams, venues, competitions, divisions, grades, seasons.
Programs: Seniors, Juniors, Women's, Girls', All Abilities, Veterans/Masters, custom.
Playing conditions configurable by competition, season and grade, with match-specific
overrides. Junior and Girls' grades default to a max of 15 players per team, subject to
actual competition rules. Unknown historical playing conditions must remain unknown.

## 9. People and profiles

Canonical People registry per workspace. Roles: players, captains, umpires, coaches,
officials, committee members, Life Members, Honorary Members (one person may hold
multiple). Preserve historical names, club affiliations, playing/captaincy/umpiring
history, photographs, research notes, source references. Provide controlled identity
merging. Never automatically merge uncertain historical identities.

## 10. Matches and scorecards

Fast spreadsheet-style scorecard entry. Support multiple innings, multi-day matches,
home & away, finals, grand finals, forfeits, draws, ties, abandoned matches, historical
playing conditions, partial scorecards, unknown values, match-only and season-only
historical records, match captains, acting captains, wicketkeepers, umpires, source
documents, research notes. Allow players to be created during scorecard entry (no
separate Playing XI screen). Support autosave, keyboard navigation and validation.

## 11. Match verification

Record states: Draft, Researching, Ready for Review, Verified, Verified Partial,
Disputed. Verified Partial must preserve the exact verified scope. Never treat missing
historical data as zero. Preserve source provenance, original evidence, verification
history, user changes, audit records. Do not silently overwrite verified records.

## 12. Data integrity and auditing

Comprehensive **Scorecard Audit Centre**. Audit for: incomplete retirements; duplicate
batters; bowlers/fielders missing from batting cards; duplicate bowlers/fielders; players
with no recorded participation; missing captains; missing wicketkeepers; incorrect
caught-and-bowled entries; fall-of-wicket inconsistencies; winning-margin
inconsistencies; missing maximum overs; overs exceeding limits; missing batting/bowling
scorecards; blank batter/bowler names; potentially inconsistent bowler/fielder
combinations; incomplete abandoned matches; incorrect innings totals; duplicate matches;
conflicting historical evidence. Classify findings as Critical, Warning, Informational,
Accepted historical exception. Provide direct navigation to affected records. Do not
automatically alter verified information.

## 13. Third-party match imports (investigate)

Candidate providers (not assumed working APIs): Play.Cricket Australia, Play-Cricket
England / ECB, PlayHQ Australia, PlayHQ New Zealand, PlayHQ Scotland, Cricket Archive,
NVPlay, CricClubs, CricHeroes. For each investigate: interfaces, authentication, export
formats, licensing, permission requirements, supported data, technical restrictions.
Design a modular connector architecture supporting match URL recognition, match ID entry,
single-match import, batch import where permitted, import preview, player/team matching,
duplicate detection, conflict resolution, administrator approval, source attribution,
import history. **Prioritise Australian PlayHQ (RMCC uses it).** Do not bypass access
controls.

## 14. Cricket Statz import and export (investigate)

Investigate Cricket Statz export files, CSV, Excel, JSON extracts, MXP files and other
documented formats. Do not assume undocumented structures; inspect actual samples before
implementation. Support safe data mapping, staging, validation, identity matching, import
approval. Preserve existing verified records.

## 15. Automatic online match discovery

Defaults: Search Entire Workspace; All Available History; Include Partial Records; Skip
Confirmed Duplicates; Administrator Approval Required. Support historical club aliases,
historical competitions, newspaper archives, cricket databases, permitted online sources,
background jobs, pause/resume, progress tracking, restart recovery, source attribution,
duplicate matching, existing scorecard enrichment, import approval. Do not impose an
arbitrary 150-year limit. Respect copyright, access restrictions and provider terms.

## 16. Research Centre

Location: Matches → Research Centre. Includes: (1) Historical Scorecards, (2) Find Matches
Online, (3) Source Library, (4) Research Gaps, (5) Review & Verify. Support historical
scorecard reconstruction, multiple newspaper editions, partial information, research
notes, save/resume, source linking, conflict comparison, verification queues, field-level
provenance. Maintain one canonical match record. Publication dates remain separate from
match dates.

## 17. Historical media archive

Support original scorecard images (JPEG, PNG, TIFF, PDF), multiple documents per match,
original-quality preservation, zoom/viewing, source metadata, copyright information,
historical significance markers, secure backup, export. Include an optional Club Heritage
Collection.

## 18. Optional OneVault integration

OneStats must work fully without OneVault. Media options: (1) OneStats Internal Storage,
(2) Optional OneVault Integration, (3) External File References. Use stable media
identifiers; respect permissions; do not automatically delete originals; allow optional
migration between supported storage providers. Do not assume OneVault already has a
working API. Design future compatibility with other One software.

## 19. Statistics engine

One deterministic statistics engine covering batting, bowling, fielding, wicketkeeping,
captaincy, umpiring, player participation, team performance, partnerships, historical
records, milestones, awards. Filter by workspace, club, competition, grade, season,
historical period, match classification, player, team. Separate Home & Away, Finals
(excluding Grand Finals), and Grand Finals where required. Use verified data; clearly
document calculation limitations.

## 20. RMCC standard reports (mandatory for initial release)

**Player careers:** Most Matches; Most Consecutive Matches; Most Wins; Longest Serving;
Most Matches Played Together.

**Team streaks:** Most Consecutive Matches Without a Loss; Without a Win; Most Consecutive
Wins; Most Consecutive Losses.

**Batting:** Top Run Aggregates; Most Runs in a Season; Top Run Scores; Most Runs in a
Match; Top Batting Averages (min 500 runs); Most Boundaries; Most Sixes; Most Fours; Most
90s; Most 40s; Most Centuries; Most Half Centuries; Top Batting Strike Rates (min 100
runs); Most Ducks; Most Consecutive Scores Without a Duck.

**Batting partnerships:** Top Partnerships by Wicket; Top Partnerships; Top Partnership
Aggregates.

**Bowling partnerships:** Most Wickets as a Bowling Partnership — 2, 3 and 4 players.
Define exact counting methodology before implementation.

**Bowling:** Top Wicket Takers; Top Bowling Averages (min 50 wickets); Most Wickets in a
Season; Best Bowling in a Match; Top Economy Rates (min 50 wickets); Top Bowling Strike
Rates (min 50 wickets); Most Expensive Bowling in an Innings; Most 5-Wicket Innings; Most
Ducks Inflicted.

**Fielding & wicketkeeping:** Top Fielder–Bowler Combinations; Top Wicketkeeping; Top
Wicketkeeping in an Innings; Top Catches; Top Run Outs.

**Captaincy:** Most Matches Captained; Most Wins as Captain; Best Winning Percentage as
Captain; Most Grand Finals Captained; Most Grand Final Wins as Captain; Most Consecutive
Wins as Captain; Captaincy by Season; Captaincy by Grade; Captaincy Win/Loss/Draw/Tie
Record; Captaincy unbeaten and winless streaks. Winning % = wins ÷ eligible matches
captained × 100; exclude abandoned matches and no-results from the default denominator;
apply documented competition rules for forfeits; support configurable minimum matches;
propose 20 matches as the initial RMCC qualification threshold (pending approval).

**Other records:** Annual leading run scorers; annual leading wicket takers; best
single-season run totals; best single-season wicket totals; highest innings and match
performances; highest partnerships by wicket; Grand Final records; player milestones;
career achievements.

Report catalogue must include match records separately for Home & Away, Finals and Grand
Finals.

## 21. Report qualification thresholds (RMCC defaults)

Batting Average: min 500 runs. Batting Strike Rate: min 100 runs. Bowling Average: min 50
wickets. Bowling Economy Rate: min 50 wickets. Bowling Strike Rate: min 50 wickets.
Captaincy Winning Percentage: proposed min 20 eligible matches. Other workspaces may
configure their own thresholds. Do not apply thresholds to unrelated reports.

## 22. Report Builder

Support standard reports, advanced reports, saved reports, favourite reports, custom
filters, multiple report selections, sorting, Top 10 and extended rankings, PDF export,
Excel export, approved website publishing, mobile-friendly display. Avoid duplicate
calculation logic.

## 23. Player milestones and achievements

Matches played, runs, wickets, catches, run outs, stumpings, captaincy, Grand Final
appearances, Grand Final wins, years of service, seasons represented. Include upcoming,
achieved, historical milestones and milestones over time. Workspace-specific thresholds.
Distinguish confirmed milestones from known minimum totals.

## 24. Player age and longevity

Youngest/oldest players; youngest/oldest debutants; average age by season; longest-serving
players; most seasons represented; first and last appearances; matches/days between
appearances. Protect dates of birth and junior information. Never calculate age rankings
using uncertain birth dates.

## 25. Awards and honour boards

Configurable MVP points, player points, club awards, season awards, Life Members, Honorary
Members, premiership teams, captains, historical achievements. Design a Club Honour Board
suitable for optional publication to the RMCC website.

## 26. Ask OneStats

Natural-language statistics assistant (e.g. "Who has scored the most runs for RMCC?",
"Which captain has the highest winning percentage?", "Who has the most wickets in Grand
Finals?", "What is the highest fourth-wicket partnership?"). Answers must use verified
deterministic calculations. Never invent statistics. Respect permissions. Show supporting
records and appropriate qualifications.

## 27. User roles and permissions

Roles: (1) Super Administrator, (2) Workspace Administrator, (3) Researcher, (4) Scorecard
Entry, (5) People Manager, (6) Reviewer, (7) Viewer. Support multiple roles per user,
custom roles, workspace-specific access, granular permissions, user deactivation, audit
logging. Protect: verified record changes, import approval, identity merging, research
verification, branding changes, user administration, website publishing.

## 28. Website publishing

Automatic statistics publishing. Initial target: RMCC's existing Lovable-built website.
Support secure read-only APIs, approved published statistics, hosted publication cache,
automatic & manual synchronisation, offline queues, retry handling, publication logs,
corrections and withdrawals, workspace-specific publishing settings. The website must
remain operational when the OneStats Windows server is offline. Do not expose draft,
disputed, private or restricted records. Do not assume the existing website has a
compatible API. Preserve the existing website design where practical.

## 29. Mobile records portal

Responsive read-only portal (iPhone, Android, tablets, desktop browsers) with player
profiles, career statistics, records, match results, historical scorecards, historical
images, search, Ask OneStats, workspace branding. Support public and authenticated
access. Protect junior and private information. Do not expose the administrative database
directly.

## 30. Windows installation and server

Design: (1) Set Up New OneStats System, (2) Connect to Existing OneStats System. Support a
central Windows server, multiple desktop clients, secure connections, LAN access, approved
remote access, backups, recovery, server migration, application updates, database
migrations. Plan future dedicated-server deployment. Cloud hosting optional.

## 31. Development roadmap (18 phases)

1. Planning & Architecture
2. Windows Desktop & Server Foundation
3. Workspaces, Onboarding & User Permissions
4. Clubs, Associations & Competitions
5. People & Profiles
6. Matches & Scorecard Entry
7. Validation, Verification & Data Integrity
8. Cricket Statz, Third-Party Match Import & File Integration
9. Automatic Online Match Discovery
10. Research Centre
11. Media Archive & Optional OneVault Integration
12. Statistics & Reporting Engine
13. Records, Rankings & Achievements
14. Ask OneStats
15. Website Publishing & Synchronisation
16. Mobile Records Portal
17. Windows, Website & Mobile Release
18. RMCC Full-Season Trial

Optional future phase: Cloud Hosting & Wider Commercial Deployment. Identify dependencies,
risks and appropriate overlap between phases.

## 32. Phase 1 deliverables (produce all 38, in `docs/`)

1. Executive project overview
2. Technical architecture
3. Technology stack assessment
4. Repository structure
5. Database entity relationship design
6. Workspace isolation architecture
7. Permissions matrix
8. Workspace onboarding specification
9. Branding and theme specification
10. Application navigation and screen map
11. Cricket organisation data model
12. People and identity model
13. Scorecard data model
14. Match verification workflow
15. Data integrity audit rules
16. Cricket Statz import architecture
17. Third-party provider feasibility matrix
18. Online match discovery architecture
19. Research Centre architecture
20. Media archive architecture
21. OneVault integration contract
22. Statistics calculation architecture
23. Complete RMCC report catalogue
24. Captaincy calculation specification
25. Partnership calculation specification
26. Milestones and achievements specification
27. Report Builder specification
28. Ask OneStats architecture
29. Website publishing architecture
30. Mobile portal architecture
31. Windows deployment plan
32. Backup and disaster recovery plan
33. Security and privacy requirements
34. Automated testing strategy
35. Detailed Phase 2 implementation plan
36. Required software and development assets
37. Risk register and outstanding decisions
38. Phase 1 acceptance checklist

Use diagrams and tables where useful.

## 33. Development rules

Prioritise accuracy; preserve original evidence; avoid invented statistics; keep unknown
values distinct from zero; protect verified data; prevent double counting; enforce
permissions; enforce workspace isolation; preserve historical context; respect external
source restrictions; keep OneVault optional; protect private and junior information; test
all statistical calculations; maintain backup and recovery procedures; use consistent,
accessible UI patterns; keep the application straightforward; support future One software
integrations. Do not assume a feature is implemented merely because it appears in planning
documentation.

## 34. First actions

1. Inspect the current OneStats project directory.
2. Audit existing code and documentation.
3. Confirm development environment readiness.
4. Identify completed work, if any.
5. Identify missing dependencies.
6. Produce the proposed technical architecture.
7. Produce the database design.
8. Produce the complete report catalogue and calculation rules.
9. Produce the 18-phase development roadmap.
10. Produce the detailed Phase 2 implementation plan.
11. Identify architectural decisions requiring approval.
12. Save all Phase 1 documentation.

Do not begin Phase 2. Do not implement production application features.

**On completion, provide:** a concise executive summary; completed deliverables;
recommended architecture; important technical decisions; outstanding questions; risks and
dependencies; Phase 2 readiness checklist. Finish with:

> **PHASE 1 COMPLETE — AWAITING APPROVAL TO BEGIN PHASE 2**

Then stop and wait for approval.

---

## Development environment (provisioned 2026-10-21)

| Tool | Version | Notes |
|---|---|---|
| OS | Windows 10 Pro 22H2 (19045) | 32 GB RAM, ~418 GB free |
| Claude Code | installed | — |
| VS Code | 1.141.2 | on PATH |
| Git | 2.45.2 | — |
| Node.js | 24.20.0 LTS | npm 11.19.0 |
| Python | 3.12.10 (`python`); 3.14.7 (`py`) | use 3.12 |
| Rust / Cargo | 1.99.1 (MSVC host) | for Tauri |
| MSVC C++ Build Tools | VS 2022, cl.exe 14.44 | for Tauri/native builds |
| Edge WebView2 | 155.0.4283.62 | for Tauri |
| PostgreSQL | 17.11 | service `postgresql-x64-17`, `localhost:5432` |

**PostgreSQL roles/db already created:**
- `postgres` — built-in superuser (admin only; password being set by the user).
- `scotney` — superuser login (personal admin; password set by the user).
- `onestats_app` — **LOGIN, NOT superuser**, owns database `onestats`; the application
  connects with this least-privilege role. Credentials are user-managed; never embed
  plaintext DB passwords in code or logs — use secure credential storage.

**Do not modify OneVault (`C:\OneVault`) or any other existing One project.**
