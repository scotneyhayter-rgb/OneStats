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
| T2 | Statistics → leading run-scorers (UI) | — | verify the UI report shows Kriss Ellis 48 (HS 48), B Walker 35, Jaxon Edwards 33, L Fitzpatrick 15, J Patterson 11 |
| F-2 | Highest Partnership named only a value | FIXED (verify in UI) | Record showed "40" with no players. Backend now resolves both batsmen → holder.player "Kriss Ellis & Trevor Quick"; ranking shows pairs. Test added; backend restarted. |
| F-3 | Records should show the player's club | OPEN (needs a rule) | Requirement: every record shows which club the holder played for. Single-match records (partnership, best bowling, highest score) → the club in that match. Career records (most runs/wickets/catches) → the player may have multiple clubs; needs a rule (all clubs vs primary). Awaiting the user's choice before implementing. |
| F-4 | Installer build (MSI) failed | FIXED path | `tauri build` failed: MSI rejects the non-numeric `-beta.1` pre-release version. Rebuilding NSIS-only (`--bundles nsis`), which has no such restriction. |
