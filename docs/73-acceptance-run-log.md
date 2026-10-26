# 73. Consolidated Manual Acceptance — Run Log

**Started 2026-10-26.** Records the user's hands-on results as we work through the consolidated programme
([62](62-deferred-acceptance-register.md)) one test at a time. I guide and record; **formal acceptance is
the user's** — no phase is marked user-accepted here.

Result key: `PASS` · `FAIL` (with note) · `BLOCKED` (needs something not yet available) · `SKIP` · `—` (not
yet run).

## Environment

- Backend: reachable at `http://127.0.0.1:8000` (health 200).
- App (frontend): `http://localhost:1420`.
- Installer/USB (INS1–INS9, DEP1–DEP9): **parked** — the app-only installer build is still running; these
  run once it finishes and on real hardware.

## Order of play (software-only first)

0. Environment readiness (launch, sign in, choose a workspace with data)
1. Statistics & report accuracy — RC1–RC15, spot-checks A1–A5
2. Player profiles, records & awards — P1–P16
3. Ask OneStats — ASK1–ASK7
4. Website publishing + member portal — PUB1–PUB10, MP1–MP4
5. Mobile portal + mobile upload — MOB1–MOB8, MU1–MU7
6. API & Integrations — INT1–INT12
7. Multi-fielder run-outs — RO1–RO4
8. Permissions/security/isolation, accessibility, performance
9. Install / USB (parked until the installer is built)

## Results

| Test | Area | Result | Notes / date |
|---|---|---|---|
| A0 | Environment readiness | PASS | 2026-10-26. Signed in. Workspace = **OneStats Sandbox** (13 matches, **2 approved**, 82 people). Stats reflect approved only, by design. |
| F-1 | Stale stats (finding) | RESOLVED | Approved-match batting had `hs`/`match_runs` unset → HS showed 0. Fixed by Recalculate: stored `hs` now 48 for Kriss Ellis; batting leaders HS 48/35/33/15/11. |
| T1 | Recalculate official statistics | PASS | 2026-10-26. Recalc populated HS/match-runs (verified in data). Idempotent, non-destructive. |
| T2 | Statistics/Records → run-scorers + records (UI) | PASS | 2026-10-26. HS populated; Records shows both batsmen on Highest Partnership, club on each record, Primary/All-clubs toggle works (user-confirmed). |
| F-2 | Highest Partnership named only a value | PASS (fixed) | Record now reads "Kriss Ellis & Trevor Quick — 40". Commit 0c3120d. User-confirmed in UI. |
| F-3 | Records should show the player's club | PASS (fixed) | Records show holder's club with selectable Primary/All-clubs toggle; partnership shows both clubs. Commit 98c5b07. User-confirmed in UI. |
| T3 | Bowling — Most Wickets (UI) | PASS | 2026-10-26. Daniel Taylor 4, L Fitzpatrick 3, Craig Patterson & W Brain tied on 2; club shown. User-confirmed. |
| T4 | Report Catalogue opens + a report renders | PASS | 2026-10-26. Lists reports; opened one rendered correctly. User-confirmed. |
| A2 | Captaincy populated (not zero) — spot-check | PASS | 2026-10-26. Glenn Cosgriff: Captained 1, Wins 1, Losses 0, 100%; GF captained/wins 0. User-confirmed (screenshot). Regression guard for BUG-002 holds. |
| P1 | Profile: career charts render | DONE (retest) | Per user choice (every innings / per-match): added per-match charts — "Runs by match" + "Cumulative runs" on Batting, "Wickets by match" on Bowling — shown when the player has ≥1 match (so single-season players now see them). Season charts unchanged. |
| P2 | Profile: Grand Finals section | — | Grand Finals tab opens and shows GF-specific stats (or a clear "no grand finals" state) — never invented |
| F-5 | Opened report rendered off-screen (bottom) | PASS (fixed) | Reports rendered below the whole catalogue → off-screen. Now scrolls into view. User-confirmed "jumps to view". Commit 2a24a31. (BASE_URL/PHASE console errors were stale HMR noise.) |
| F-6 | Add Match Format to report filters | PASS (catalogue) + DONE (Statistics, retest) | Format dropdown on the Report Catalogue report view (PASS, ebdc951). Per user request, also added to the Statistics leaderboards screen (Batting/Bowling/Fielding/Captaincy/Appearances/Teams) + saved-report config, for consistency across all reports. Also fixed the Statistics PDF export (same BUG-006 popup-block). Retest the Statistics screen. |
| A3 | Player-profile PDF export | PASS (fixed) | Was FAIL ("does not open" — popup-blocked window.open; BUG-006). Fixed via `openBlobUrl` anchor download across all exports. User-confirmed: PDF downloads & opens with correct info. Commit 86789d3. |
| F-7 | Open player → go to profile directly | DONE (retest) | Clicking a player card now opens the full career profile; a "Details" button opens the identity/edit panel (biography, affiliations, merge, + the new attr editors). |
| F-8 | Numbers/Leadership/Recognition editable | DONE (retest) | Added inline "+ Add" controls in the identity panel for squad Numbers, Leadership roles and Recognition (wires the existing backend endpoints). Add-only (no delete endpoint yet). |
| F-9 | Profile: first/most-recent match + opposition | DONE (retest) | Added to full_profile a `span` (first & last match by date, with the opposition club) — backend query joins match_team→team→organisation. Shown on the Overview tab. Verified Kriss Ellis: 2019-10-19 v Wickliffe/Lake Bolac. |
| F-10 | Profile: batting/bowling style | DONE (retest) | Fields existed on person_profile but weren't shown/edited. Now shown on Overview (Batting/Bowling) and editable in the identity panel ("Profile & playing style"). |
| F-11 | Richer player-profile career breakdowns | DONE (retest) | Added 4 profile tabs (OneStats-native, approved data): **Splits** (batting+bowling by opposition/ground/grade/format, selectable), **Best** (top batting innings + bowling figures), **Partnerships** (player's top stands), **Analysis** (run-scores chart, score-frequency, how-out, dismissed-by). New `player_analysis` domain + `/people/{id}/analysis` endpoint. Verified on Kriss Ellis (best 48 v Wickliffe/Lake Bolac; 40-run stand w/ Trevor Quick). |
| T5 | Fielding records (Most Catches) | PASS | 2026-10-26. Players tied on 1 catch shown correctly; tie preserved. User-confirmed. |
| P2 | Grand Finals section | PASS | 2026-10-26. 0 approved grand finals → clean empty state, no crash. User-confirmed. |
| F-12 | Add a profile photo | DONE (retest) | Added upload/remove in the Details panel ("Photo" section; JPEG/PNG/WebP) wiring the existing backend endpoints. The primary photo shows in the profile header avatar, auto-sized to fill the circle (object-cover). |
| F-4 | Installer build (MSI) failed; NSIS built | DONE (app-only) | `tauri build` MSI target rejects the non-numeric `-beta.1` version. NSIS-only build **succeeded**: `OneStats_1.0.0-beta.1_x64-setup.exe` (~212 MB, SHA-256 8042a917…4e97e) in `OneStats-USB-Installation/PLACE-INSTALLER-HERE/`. **App-only** (no PG/backend) — good for connect-to-server clients. Not code-signed. MSI + sidecar still outstanding. |
