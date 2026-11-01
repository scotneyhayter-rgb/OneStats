# Multi-user management & role-based dashboards — manual acceptance guide

How to review the new multi-user, role-based dashboard system in the dev preview. No installer
rebuild is required — run the desktop app in dev mode and sign in as the accounts below.

## Before you start
- Run the backend (FastAPI) and the desktop app in dev mode as usual.
- You need the **Super Admin** account you set up, plus (optionally) one extra account per role to
  see each role's view. Create accounts in **Settings → System Administration → Users** (Super
  Admin only), then assign roles per workspace (see "Set up test accounts" below).
- Canonical role names in the UI: **Organisation Admin** (workspace_admin), **Scorecard Editor**
  (scorecard_entry), **Data Verifier** (reviewer), **Researcher**, **Viewer / Analyst**, **Super
  Admin**.

## Set up test accounts (Super Admin)
1. Sign in as the Super Admin.
2. **Settings → System Administration → Users → New user**. Create e.g. `editor1`, `verifier1`,
   `researcher1`, `viewer1`, `orgadmin1`. Each gets a one-time temporary password (shown once) —
   note it; the user must change it on first login.
3. Assign each to **Rhymney/Moyston CC** with the matching role (Users → the user → add workspace
   role; or the workspace's Members screen). Roles are per workspace.
4. Sign out, then sign in as each test account (first login forces a password change) to review.

---

## A. Super Admin — the full flow
1. **Sign in** as the Super Admin. The sidebar workspace selector shows an **"All Workspaces"**
   entry plus every workspace with its logo; it is searchable.
2. **All Workspaces** → platform overview:
   - Platform summary cards (workspaces, users, Super Admins, and **workspace record** totals).
   - Confirm the caption: totals are *workspace record counts*, not global-unique.
   - **Organisation comparison** table — click a column header to sort; click an organisation to
     drop straight into that workspace.
   - **System health** (database, maintenance mode, active sessions, version) and **Platform
     activity** (recent account actions).
3. **Select Rhymney/Moyston CC** from the selector. You are now in that workspace. Because you are
   a Super Admin with no ordinary membership there, a banner reads **"Super Admin — Managing
   Rhymney/Moyston CC. Actions are recorded against your own account."**
4. Exercise full control in the workspace (all should work, not be read-only):
   - Matches/scorecards (create, edit, submit, approve), People (incl. merges), Competitions/
     Seasons/Grades/Venues, Research Centre, Media, Records, Publishing.
   - **Settings → Users / Branding / workspace config**.
   - Audit: changes you make are recorded against **your** Super Admin identity (not the local
     admin), with `acting_as_super_admin` set.
5. **Switch directly** to another workspace from the selector — the dashboard and all figures
   refresh to that workspace; no data from the previous workspace leaks in.
6. **Return to All Workspaces** via the selector.

Expected: fast switching; the Managing banner appears only inside a workspace you are not an
ordinary member of; the platform view never appears for non-Super-Admins.

## B. Organisation Admin
1. Sign in as `orgadmin1` (Organisation Admin of Rhymney/Moyston CC).
2. No "All Workspaces" entry (not a Super Admin). The dashboard shows everything: summary, My Tasks,
   quick actions (Add Match, Import, Research, Media, Review Approvals, Sync), research progress.
3. Sidebar shows the full Club Management group.
4. **Settings → Users** lets you manage members *within this workspace* (not platform-wide).
Expected: full workspace control; cannot see other workspaces or platform admin.

## C. Researcher
1. Sign in as `researcher1`.
2. Sidebar: Dashboard, Matches, People, Statistics, Ask, **Research Centre**, (Records, Portal).
   No Settings, no Import/AutoSync/Organisations/Competitions/Publishing.
3. Dashboard **My Tasks** shows open research tasks and research conflicts (not approvals).
4. Research Centre works (create/progress tasks, sources, projects). You **cannot** approve/verify
   findings or change verified statistics.
Expected: research tools available; approval/verification actions absent.

## D. Scorecard Editor
1. Sign in as `editor1`.
2. Dashboard quick actions include **Add Match** (not Review Approvals). My Tasks shows **draft /
   incomplete scorecards** you can finish.
3. Create a draft match, enter batting/bowling, then **Submit for approval**.
4. Confirm there is **no Approve** control for you — an editor cannot approve their own work.
Expected: can draft and submit; cannot approve (verification not bypassable).

## E. Data Verifier
1. Sign in as `verifier1`.
2. Dashboard **My Tasks** shows **scorecards awaiting approval**. A card you submitted yourself is
   tagged **"you submitted"** (a reminder that a different verifier should approve where possible).
3. Open an awaiting scorecard → **Approve** (or return/reject). Confirm the approval history records
   you as the approver.
Expected: can approve/return; sees the verification queue; self-submitted items are flagged.

## F. Viewer / Analyst
1. Sign in as `viewer1`.
2. Sidebar: Dashboard, Matches, People, Statistics, Ask, (Records, Portal). No management sections,
   no Settings, no quick-action editing buttons, and **no My Tasks** section.
3. You can view profiles/reports/records, run Ask OneStats and export authorised reports. There are
   no edit/approve controls anywhere.
Expected: read-only analyst experience.

## G. Dashboard customisation (any role)
1. On the Dashboard, click **Customise**.
2. Toggle **Summary / Historical research / Recent activity** off and on — the choice saves to your
   account for this workspace and persists on reload.
3. Confirm you **cannot** hide My Tasks, quick actions, or (as Super Admin in a managed workspace)
   the "Super Admin — Managing…" banner — critical/security sections are never hideable.

## H. Themes & branding
- Switch the theme (Settings/appearance) across the 8 themes; the dashboards and new screens follow
  the theme and the workspace's branding (logo/colours) with no broken contrast.

## What to check overall
- Switching dashboard **view** never grants extra permission — a viewer stays read-only even after
  visiting other screens.
- Every figure matches the reports (same stats engine); unknown values show as unavailable, never as
  a fabricated zero.
- Nothing you could do before is missing (Research Centre, reports, imports, etc. all intact).
