# Phase 7 — Manual Acceptance Checklist (Stage 7.11)

> **Status: ACCEPTED — 2026-10-25.** Walked through in the OneStats Sandbox. Tests 1–11 confirmed by
> the user; Test 12 (workspace isolation) is enforced by FORCE RLS and covered by automated isolation
> tests. Defects found during acceptance were fixed and re-tested (captains/keepers import; toss
> import; FOW batter scoping + inline advisory highlights; one-click confirm-total; Result dropdown
> capitalisation; match-date field flashing; season back-fill on rule change). See the Development
> Dashboard for the commit list. Final suites green: 360 backend / 52 desktop.


For a non-technical reviewer, in the **OneStats Sandbox** workspace. No production or other
workspace records are modified. Start the app and backend (see below), sign in, open the Sandbox.

## Startup (Windows)
Backend (new terminal):
```bash
cd C:/OneProjects/OneStats/services/api
./.venv/Scripts/python -m uvicorn onestats.main:app --host 127.0.0.1 --port 8000 --log-level warning
```
Desktop app (another terminal):
```bash
cd C:/OneProjects/OneStats/apps/desktop
npm run dev
```
Then open the app (the in-app browser / `http://localhost:1420`). If the screen is blank after a
pull: `rm -rf apps/desktop/node_modules/.vite` and restart `npm run dev`.

## Checklist

1. **Automatic partnerships (no button).** Open a match → an innings → Fall of Wickets. Enter a FOW
   sequence (team scores + dismissed batters). Confirm **Partnerships populate automatically** and
   name both batters; there is **no Auto-generate button**.
2. **Incorrect FOW warning.** Make a FOW score decrease (e.g. wicket 2 lower than wicket 1). Confirm
   an advisory warning appears in **Scorecard Approval → Validation** ("FOW scores not increasing"),
   and the scorecard still saves (incomplete/odd historical data stays valid).
3. **Automatic winning margin.** Enter two innings with official totals (e.g. 150 then 120 all out).
   Confirm the Result shows **"<Home> won by 30 runs"** with an **Auto-calculated** badge.
4. **Season preserved.** Set the competition's **Season rule** (Settings/Competitions) to Australian
   summer; confirm a new match's season auto-fills (e.g. a January 2024 match → 2023/24). Change the
   season manually on a match; confirm a later edit **does not overwrite** your choice.
5. **Match format respects settings.** In **Settings → Match Formats**, disable some formats and set
   a default. Confirm the scorecard **Format dropdown shows only enabled formats** and a new match
   defaults to your choice. A match already using a now-disabled format still shows it.
6. **Historical team name correction.** In Teams, open a team, use **Rename**. Confirm the display
   name updates everywhere, the **previous name is kept as an alias**, and the **original imported
   source name** is still shown.
7. **Australian / English score display.** In **Settings → Scorecard Display**, switch between
   Australian (10/127) and English (127/10). Confirm the **prominent innings score and the innings
   tabs** update; set a personal preference and confirm it applies to your view.
8. **Approval permissions & transitions.** On a match, use **Scorecard Approval**: Submit for
   approval → Approve (admin) / Reject with a reason → Resubmit → Reopen. Confirm the **approval
   status is separate from the match status**, reasons are recorded, and a non-admin cannot approve.
9. **Approved = official; recalculation no duplicates.** Approve a scorecard; open the player's
   **official stats** (or run **Settings → Recalculate official statistics**) and confirm the figures
   appear. Edit the approved scorecard; confirm official stats **keep the last approved version**
   (the match shows "revised since approval"); re-approve and confirm they **update without
   doubling**.
10. **Player selection scoping.** On a batting/bowling/captain field, confirm the dropdown shows the
    **relevant club's players** by default, with a **"Show all players"** toggle that reveals
    everyone (fill-ins / other clubs) — no transfer or duplicate identity is forced.
11. **CricketStatz import compatibility.** Open **Club Management → Import Data**, choose the
    CricketStatz JSON, preview a small slice, import, open a match, and confirm the scorecard,
    dismissals (raw codes preserved), FOW and auto-partnerships are correct. Re-run the import and
    confirm **no duplicates**.
12. **Workspace isolation.** Confirm all of the above is confined to the Sandbox workspace.

Report any step that does not behave as described. Known limitation: the full Competition Points
Manager and ladders, and the complete statistics/records/milestones reporting modules, are later
phases — Phase 7 provides the approved-only recalculation foundation they build on.
