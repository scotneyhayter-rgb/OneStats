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
| A2 | Captaincy populated (not zero) — spot-check | — | Glenn Cosgriff profile should show captaincy: 1 captained, 1 win, 100% (regression guard for old BUG-002) |
| F-5 | Opened report rendered off-screen (bottom) | PASS (fixed) | Reports rendered below the whole catalogue → off-screen. Now scrolls into view. User-confirmed "jumps to view". Commit 2a24a31. (BASE_URL/PHASE console errors were stale HMR noise.) |
| F-6 | Add Match Format to report filters | PASS (done) | Format dropdown appears next to the split with the enabled formats; applies to report + PDF/CSV. Commit ebdc951. User-confirmed. (Sandbox: specific pick → 0 rows until matches have a format.) |
| A3 | Player-profile PDF export | FAIL→FIXED (retest) | "Does not open." Backend produced a valid PDF (request 200 OK); the UI called `window.open(blobURL)` AFTER an await, so the popup blocker stopped it. Fixed: all PDF/CSV exports (profile, record book, report PDF/CSV, catalogue index) now download via a programmatic anchor (`openBlobUrl`). **BUG-006.** Retest: should now download/open. |
| T5 | Fielding records (approved data) | — | expect empty/sparse: no catches recorded in the 2 approved matches (correct, not a bug) |
| F-4 | Installer build (MSI) failed; NSIS built | DONE (app-only) | `tauri build` MSI target rejects the non-numeric `-beta.1` version. NSIS-only build **succeeded**: `OneStats_1.0.0-beta.1_x64-setup.exe` (~212 MB, SHA-256 8042a917…4e97e) in `OneStats-USB-Installation/PLACE-INSTALLER-HERE/`. **App-only** (no PG/backend) — good for connect-to-server clients. Not code-signed. MSI + sidecar still outstanding. |
