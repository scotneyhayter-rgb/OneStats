# Super Admin User Management & First-Login — Audit & Implementation Report

**Date 2026-10-26.** Audited the existing authentication, user-management and permissions implementation,
then implemented the missing essential capabilities. No working functionality was duplicated. No phase is
marked user-accepted.

## 1. Audit — what already existed

- **Password security:** Argon2id hashing (never plaintext), automatic rehash; session tokens stored only
  as SHA-256 hashes, with TTL + revoke.
- **Authentication:** `authenticate` (active-status check), `last_login_at`, session create/validate/revoke.
- **Secure first-run bootstrap:** setup-token flow creates the initial Super Admin — **no hard-coded
  credentials** (token generated on first run, written to a local operator file).
- **Permissions:** built-in roles (super_admin, workspace_admin, researcher, scorecard_entry,
  people_manager, reviewer, viewer); `grant_role`/`revoke_role`; **backend enforcement** via
  `require_permission` / `require_super_admin`.
- **Workspace membership:** `add_member` (grant role, `user.admin`), `list_members`; audit logging.
- **Workspace isolation:** database-level FORCE RLS (verified earlier).
- **Connection config (Phase 17):** standalone vs connect-to-server, with a first-run gate.

## 2. Implemented now (the gaps)

- **System Administration → User Management screen** (Super-Admin only): list/create/edit/suspend users,
  assign system + workspace roles, invitations, reset passwords, audit view.
- **Temporary single-use expiring passwords** + **forced first-login change** (`must_change_password`,
  `password_expires_at`; a used/expired temp can't be reused; change-password endpoint + screen).
- **Time-limited invitations** (create/list/revoke/**accept** via single-use token) as an alternative to
  temp passwords.
- **Suspend / reactivate** accounts (sessions revoked on suspend); **password reset** (new temp + sessions
  revoked).
- **System & workspace role assignment** (cross-workspace, Super-Admin), with revoke.
- **Login/admin audit view** (`login_attempt` + `admin_audit` global tables).
- **Rate limiting** of failed logins (per username, windowed; a success resets).
- **Escalation guards:** `super_admin` can never be granted as a workspace role; only a Super Admin sets
  the system Super Admin flag; the **last active Super Admin cannot be suspended or demoted**.
- **Secure Super Admin recovery:** operator-issued one-time recovery token (host access required) →
  `/setup/recover-super-admin`; cannot be triggered remotely; never bypasses auth or workspace isolation.
- **Backend-first enforcement** throughout; `/auth/me` and login now surface `must_change_password` so the
  desktop forces the change.

Schema: migrations **0053** (`must_change_password`, `password_expires_at`, `user_invitation`,
`login_attempt`) and **0054** (`admin_audit`) — all **global** platform tables, no plaintext secrets.

## 3. Security properties

Never stores plaintext passwords (Argon2id); temporary/recovery credentials are single-use and expire;
password-strength floor (≥10 chars, a letter + a number); login rate-limited; admin actions + login
attempts audited; permissions enforced in the backend (not only the UI); Club Admins cannot grant
system-wide Super Admin; recovery cannot bypass authentication or workspace isolation.

## 4. Automated tests

- `tests/test_user_management.py` (9): temp-password + first-login change; temp expiry; strength; suspend/
  reactivate + last-admin guards; escalation guard; rate limiting; invitation single-use + revoke;
  recovery (single-use, invalid rejected); audit history.
- Desktop `features/admin/user-management.test.tsx` (2); `features/settings/connection-settings.test.tsx` (1).
- Existing auth/permission/workspace suites remain green.

## 5. What remains (honest)

- **Manual acceptance** of the above (USR1–USR12 in the deferred register) — deferred with the rest.
- **Invitation delivery** is by token (shown to the admin to pass on / an accept screen); automated email
  delivery is out of scope until a mail transport is chosen.
- **Account-recovery operator command** is a server-side function; wiring it to a packaged CLI entry point
  is a small release-engineering follow-up (the endpoint + token mechanism are implemented and tested).
- The connect-to-server **certificate validation** relies on the OS/TLS trust store for HTTPS server URLs;
  a custom-CA/cert-pinning option is a follow-up if RMCC uses a private CA.

Proceeding with the approved roadmap. **No phase is marked user-accepted.**
