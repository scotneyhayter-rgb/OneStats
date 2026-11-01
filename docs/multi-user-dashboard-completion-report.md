# Multi-user management & role-based dashboards — completion report

Date: 2026-11-01 · Branch: `phase-2-foundation` · Commits: `2826216` (B+C), `5092949` (D),
`856cd36` (E), `0e42e18` (F), `abbe3a1` (G), plus this report.

## 1. Existing architecture & what changed
OneStats already had a mature foundation, so this work **reused** it and filled gaps rather than
rebuilding:

Already present (reused): RBAC tables (`permission`/`role`/`role_permission`/
`app_user_workspace_role`), the global Super-Admin flag with an escalation guard, FORCE
Row-Level-Security workspace isolation (fail-closed, `SET LOCAL`, non-owner `onestats_app`),
Super-Admin user management (create/invite/suspend/reset/audit, last-super-admin protection), a
real workspace dashboard using the authoritative stats engine, and the audit log.

Changed/added:
- **Role-grant reconciliation** (migration `0062`) so the six roles are genuinely functional — the
  granted permissions had drifted from what endpoints enforce (`match.manage`, `scorecard.approve`,
  `person.manage`, `research.manage`/`research.verify`).
- **Per-workspace permissions** returned by `GET /workspaces`; the client gates nav + actions on
  them (backend stays the authority).
- **Richer audit context** (migration `0060`): actor role, effective permission, reason, request id,
  `acting_as_super_admin`; a request-id middleware; the actor is always the real user.
- **Submitter capture + self-approval flag** (migration `0061`).
- **Platform "All Workspaces" dashboard** (`/platform/dashboard`).
- **Unified My Tasks** (`/workspaces/{id}/tasks`) reusing the verification queue + Research Centre.
- **Per-user dashboard customisation** (migration `0063` + `/me/preferences`).

## 2. The six roles & permissions
| Spec role | Built-in key | Can | Cannot |
|---|---|---|---|
| Super Admin | `super_admin` (flag) | everything, in any workspace, without membership | n/a |
| Organisation Admin | `workspace_admin` | manage the whole workspace | onboard a new workspace |
| Researcher | `researcher` | research (`research.manage`), people (`person.manage`), investigate identity | approve/verify (`research.verify`), approve scorecards |
| Scorecard Editor | `scorecard_entry` | create/enter/submit scorecards (`match.manage`) | approve (`scorecard.approve`) — can't bypass verification |
| Data Verifier | `reviewer` | approve/return scorecards, verify research, check identities | workspace admin / user admin |
| Viewer / Analyst | `viewer` | view, Ask OneStats, export | any edit/admin |

A legacy `people_manager` role is retained (not one of the six). Multiple roles per user are
supported and permissions are the **union** for the currently selected workspace; switching which
dashboard you view never grants permission.

## 3. Super Admin demonstration
- **All Workspaces**: searchable selector (logos) + a platform dashboard — summary, sortable
  organisation-comparison table, system health, platform activity. Totals are labelled **workspace
  record counts** (the same match/player can appear in several workspaces).
- **Individual workspace**: selecting one gives full administrative control (matches, scorecards,
  people incl. merges, competitions/seasons/grades/venues, research, users, settings/branding,
  audit) — not blocked by lack of ordinary membership.
- **Switching**: direct workspace-to-workspace and back to All Workspaces; views refresh.
- **Identity & attribution**: a banner reads "Super Admin — Managing [Workspace]"; the Super Admin
  keeps their own identity and is **never** recorded as the local Organisation Admin — every audited
  action stores the real user id, role, effective permission, workspace, before/after, reason and
  request id, with `acting_as_super_admin` set.

## 4. Each role's dashboard
One shared dashboard architecture (reusable parts: header, overview, My Tasks, activity, quick
actions) adapts by permission — not six separate UIs. Viewer = read-only summaries; Editor = drafts
+ Add Match; Verifier = approval queue; Researcher = research tasks/conflicts; Org Admin = all; Super
Admin = all + the platform view. My Tasks is the single unified surface (verification queue +
Research Centre), role-filtered server-side, with self-submitted scorecards flagged.

## 5. Security & isolation enforcement
- Server-side Super-Admin pathway only (the `is_super_admin` DB flag); no client-controlled
  escalation; workspace selection validated server-side; FORCE RLS stays enabled (the platform
  dashboard iterates per workspace, never disables RLS or uses a bypass role).
- No privileged DB credentials reach the client; the runtime connects as non-owner `onestats_app`.
- Sensitive actions are audited with full actor context.

## 6. Actual test results (including failures)
- **Backend** (`pytest`, live dev DB, FORCE RLS): **728 passed, 2 skipped, 4 failed**. All 19 new
  tests for this work pass: `test_roles_security` (13), `test_platform` (2), `test_my_tasks` (2),
  `test_preferences` (2).
- **Frontend** (`vitest`): **107 passed**; `tsc` clean; production build (`tsc && vite build`) ok.
- **The 4 backend failures are pre-existing and unrelated** to this work (confirmed by re-running
  them with these changes `git stash`ed):
  1. `test_audit_stats_reference::test_bowling_reference_with_eight_ball_overs`
  2. `test_integrity_economy_keepers::test_economy_flagged_when_over_length_unrecorded`
  3. `test_cricket_statz_adapter::test_normalize_scorecard_dismissals_fow_and_unknown_not_zero`
  4. `test_workspaces::test_create_and_duplicate_prevention` (the dev DB already contains an `rmcc`
     workspace, so the duplicate-prevention assertion trips on live state)

## 7. Data-integrity protections
- All dashboard figures come from the authoritative stats engine / consistent COUNT queries; no
  per-dashboard calculations that disagree with reports.
- Unknown historical values are never shown as zero; unavailable states are shown instead.
- Approved vs draft is distinguished; only approved/`verified_partial` + `include_in_statistics`
  matches are official.
- Drafts stay bound to their workspace (verified by test); rapid switching cannot cause
  cross-workspace writes (every write runs inside a validated workspace transaction).
- Customisation can never hide critical/security sections (enforced in code).

## 8. Outstanding limitations / recommendations
- **Live browser acceptance** is for the reviewer (see `multi-user-dashboard-acceptance.md`) — not
  run here to avoid disrupting the dev server already open in the folder.
- **Pre-existing economy bug** (failures 1–2 above): economy is not scaled by `over_length` (assumes
  6-ball overs). Out of scope for this task but worth a separate fix.
- **My Tasks** reuses existing counts/rows; a richer per-item notification stream (e.g. assignment
  notifications) could build on it later.
- The audit context is threaded into the highest-value endpoints (membership, platform, approvals);
  threading `audit_kwargs` through every remaining mutating endpoint is a mechanical follow-up.
- Client-side caches: queries are keyed to the selected workspace and refetched on switch; a formal
  shared cache layer (if one is later added) should include workspace + auth in its keys.

## 9. Manual review
Step-by-step scripts for Super Admin (All Workspaces, Rhymney/Moyston, another workspace), Org Admin,
Researcher, Scorecard Editor, Data Verifier and Viewer/Analyst are in
**`docs/multi-user-dashboard-acceptance.md`**.
