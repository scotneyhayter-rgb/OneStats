# 7. Permissions Matrix

**Deliverable 7 of 38**

Seven built-in roles (§27), multiple roles per user, custom roles, workspace-specific
access, granular permissions, user deactivation and audit logging. Permissions are
enforced in the **service layer** on every mutating and sensitive-read path, on top of
workspace isolation (deliverable 6).

## 7.1 Roles

| # | Role | Scope | Purpose |
|--:|---|---|---|
| 1 | **Super Administrator** | All workspaces | Create/onboard workspaces, manage users globally, all actions. Only cross-workspace role. |
| 2 | **Workspace Administrator** | One workspace | Full control within a workspace incl. branding, users, publishing. |
| 3 | **Researcher** | One workspace | Historical research, source library, reconstruct scorecards, propose verification. |
| 4 | **Scorecard Entry** | One workspace | Enter/edit draft scorecards and matches. |
| 5 | **People Manager** | One workspace | Manage people/profiles; propose (not auto) identity merges. |
| 6 | **Reviewer** | One workspace | Review & verify records; approve imports; resolve conflicts. |
| 7 | **Viewer** | One workspace | Read-only access to permitted (non-private) data. |

Users may hold several roles (effective permissions = union). Custom roles are
workspace-scoped bundles of the granular permissions below.

## 7.2 Protected actions (§27 — require explicit permission + audit)

Verified-record changes · import approval · identity merging · research verification ·
branding changes · user administration · website publishing.

## 7.3 Granular permission matrix

Legend: ✅ allowed · 👁 read-only · ➖ none · ✎ draft/propose only (no verify/approve).

| Permission | Super | Wksp Admin | Researcher | Scorecard | People Mgr | Reviewer | Viewer |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| Create/onboard workspace | ✅ | ➖ | ➖ | ➖ | ➖ | ➖ | ➖ |
| Manage workspace settings | ✅ | ✅ | ➖ | ➖ | ➖ | ➖ | ➖ |
| Change branding/theme | ✅ | ✅ | ➖ | ➖ | ➖ | ➖ | ➖ |
| User administration | ✅ | ✅ (own wksp) | ➖ | ➖ | ➖ | ➖ | ➖ |
| View matches/stats (non-private) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 👁 |
| Enter/edit **draft** scorecards | ✅ | ✅ | ✎ | ✅ | ➖ | ✎ | ➖ |
| Edit **verified** records | ✅ | ✅ | ➖ | ➖ | ➖ | ✅ | ➖ |
| Verify / change verification state | ✅ | ✅ | ➖ | ➖ | ➖ | ✅ | ➖ |
| Manage people/profiles | ✅ | ✅ | ✎ | ✎ | ✅ | ➖ | ➖ |
| Propose identity merge | ✅ | ✅ | ✅ | ➖ | ✅ | ✅ | ➖ |
| Approve/execute identity merge | ✅ | ✅ | ➖ | ➖ | ➖ | ✅ | ➖ |
| Undo merge / split player | ✅ | ✅ | ➖ | ➖ | ➖ | ✅ | ➖ |
| Mark "Definitely Different" | ✅ | ✅ | ✅ | ➖ | ✅ | ✅ | ➖ |
| Resolve same-match identity conflict | ✅ | ✅ | ➖ | ➖ | ➖ | ✅ | ➖ |
| Run/record research | ✅ | ✅ | ✅ | ➖ | ➖ | ✅ | ➖ |
| Approve research verification | ✅ | ✅ | ➖ | ➖ | ➖ | ✅ | ➖ |
| Configure import connectors | ✅ | ✅ | ➖ | ➖ | ➖ | ➖ | ➖ |
| Run import (to staging) | ✅ | ✅ | ✅ | ✅ | ➖ | ✅ | ➖ |
| **Approve** import → canonical | ✅ | ✅ | ➖ | ➖ | ➖ | ✅ | ➖ |
| Manage media assets | ✅ | ✅ | ✅ | ✎ | ✎ | ✅ | ➖ |
| Configure website publishing | ✅ | ✅ | ➖ | ➖ | ➖ | ➖ | ➖ |
| **Approve** publish / withdraw | ✅ | ✅ | ➖ | ➖ | ➖ | ✅ | ➖ |
| View protected junior/DOB data | ✅ | ✅ | ⚠️ as granted | ⚠️ as granted | ✅ | ⚠️ as granted | ➖ |
| Export (PDF/Excel) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ as granted |
| Ask OneStats (deterministic) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 👁 |

`⚠️ as granted` = off by default; grantable per-user/role for that workspace. Junior and
private information is protected by default (deliverables 24, 33).

## 7.4 Enforcement model

- **Where:** service layer decorators/dependencies check
  `(user, workspace, permission)` on every mutating/sensitive endpoint. The UI hides
  disallowed actions but is **never** the enforcement point.
- **Deactivation:** deactivated users keep their audit history but lose all access
  immediately; no hard delete of the user record (provenance of who did what).
- **Audit:** every protected action writes an append-only `audit_log` entry
  (actor, action, before/after, workspace, timestamp).
- **Least privilege at the DB:** regardless of app role, all access is via
  `onestats_app` (non-superuser) under RLS (deliverable 6). App roles never map to
  PostgreSQL roles.

## 7.5 Decisions

- `[DECISION D3]` Confirm default visibility of junior/DOB data per role (recommend:
  hidden by default, grantable to Workspace Admin + People Manager).
- Custom-role granularity: start with the permission set above; extend as real RMCC
  workflows surface needs.
