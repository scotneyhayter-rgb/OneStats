# 74. OneStats Update System — Design, Status & Runbook

**Created 2026-10-26.** Secure update management for OneStats (Windows-first): desktop app, main
server, PostgreSQL database and release distribution. This document is the authority for the
versioning scheme, compatibility rules, signing/hosting requirements and the server-update runbook.

> **Status honesty.** Nothing here is claimed as *operational on installed Windows computers*. Each
> capability is tagged: **IMPLEMENTED IN CODE**, **AUTOMATED TESTS PASSED**, **REQUIRES WINDOWS
> INSTALLATION TESTING**, **REQUIRES HOSTING/SIGNING CONFIGURATION**, or **NOT YET IMPLEMENTED**.

## 1. Versioning scheme

Independently versioned components (single sources of truth in parentheses):

| Component | Source of truth | Current |
|---|---|---|
| Desktop app | `apps/desktop/src-tauri/tauri.conf.json` (+ `package.json`, `src/lib/version.ts`) | `1.0.0-beta.1` |
| Server | `services/api/onestats/core/version.py` → `SERVER_VERSION` (`onestats.__version__`) | `1.0.0-beta.1` |
| API contract | `core/version.py` → `API_VERSION` (integer; bump only on a breaking API change) | `1` |
| Database schema | Alembic head (`core/version.py` → `DB_SCHEMA_HEAD` / `DB_SCHEMA_LEVEL`) | `0058_update_system` / `58` |

Compatibility is decided by the **API version** and the **explicit min/max desktop rules** in
`core/version.py` — never inferred from the marketing version string alone. Semantic-version
comparison (incl. prerelease ordering) lives in `core/version.py::compare_versions`.

## 2. Client/server compatibility handshake — **IMPLEMENTED IN CODE · AUTOMATED TESTS PASSED**

- `GET /api/v1/capability` (authenticated): minimal capability document — server/API versions, channel,
  DB schema (current vs expected), min/max desktop, maintenance state. No infrastructure details.
- `GET /api/v1/updates/compatibility?desktop_version=…`: evaluates a client against the server and
  returns `status` (`ok` | `desktop_too_old` | `desktop_too_new` | `maintenance` | `unknown`),
  `can_operate`, `required_action` and a user-facing `message`.
- Desktop: **Settings → Updates & Version** reads these on open and on “Check for updates”, and shows a
  compatibility banner. Rules: too-old desktop → must update; too-new desktop → server must update;
  maintenance → wait; service unavailable → continue if known-compatible (never guess).

## 3. Desktop updater — **PARTIAL (REQUIRES HOSTING/SIGNING + WINDOWS INSTALLATION TESTING)**

The secure download/verify/install flow uses the **official Tauri 2 updater** (no custom executable
downloader). Prepared vs. outstanding:

- **IMPLEMENTED IN CODE:** Updates & Version UI (versions, channel, last check, status, manual check,
  compatibility banner); the update-status state machine; honest “no update service configured” state;
  release-manifest + checksum generator (`scripts/build-release-manifest.py`) producing our rich
  manifest **and** a Tauri `latest.json` skeleton.
- **REQUIRES SIGNING CONFIGURATION:** add `tauri-plugin-updater` to `src-tauri` with a `plugins.updater`
  block (`endpoints`, trusted `pubkey`). Generate the updater keypair with `tauri signer generate`;
  keep the **private key out of the repository** (CI secret / protected store); the public key is
  embedded in the app. Optionally add Windows **Authenticode** signing (distinct from the updater
  signature) — a paid certificate, **not purchased without approval**.
- **REQUIRES HOSTING CONFIGURATION:** publish signed artifacts + `latest.json` to an approved HTTPS
  endpoint; set `ONESTATS_RELEASE_MANIFEST_URL` (server) and the updater `endpoints` (desktop).
- **REQUIRES WINDOWS INSTALLATION TESTING:** download, signature verification, install and restart on a
  real installed build (UP-08..UP-13).

Enabling the plugin requires an installer rebuild, which is **deferred** during functional acceptance
(per the development rules). The config and scripts are prepared so the updater drops into the final build.

## 4. Server update system — **PARTIAL (control plane IMPLEMENTED; execution REQUIRES WINDOWS SERVICE)**

Super-Admin only (`require_super_admin`). Workspace admins do **not** get server-update authority.

- **IMPLEMENTED IN CODE · AUTOMATED TESTS PASSED (auth-gating):**
  - **Super Admin → System Updates** dashboard: server/API/schema versions, channel, backup readiness
    (destination + free space), release-service config, recent events / last result.
  - **Pre-update checks** (`POST /system/updates/pre-check`): DB connectivity, schema known, backup
    destination writable, sufficient disk space (>500 MB), not already in maintenance. Returns a
    ready/not-ready gate; records an audit event.
  - **Maintenance mode** (`POST /system/updates/maintenance`): a `system_state` flag. While on, a
    request middleware rejects **writes** (POST/PUT/PATCH/DELETE) with `503` across all workspaces, so
    no scorecard/data change lands mid-migration; **reads stay available**. Auth, setup and the
    system-update routes are exempt so an admin can sign in and exit maintenance.
- **NOT YET IMPLEMENTED / REQUIRES WINDOWS SERVICE:** actually applying a verified server package,
  running approved migrations, draining connections, restarting services and post-update health checks.
  This must run through a **least-privilege, dedicated maintenance mechanism** (a Windows service or
  elevated maintenance task) — **never** by giving the desktop app unrestricted admin rights, and
  **never** via an arbitrary-command endpoint in the ordinary API.

## 5. Database protection — **IMPLEMENTED IN CODE (checks) · migration exec via Alembic**

- Backups: `backup_readiness()` verifies a writable destination (`<media_root>/backups` or
  `ONESTATS_BACKUP_DIR`) and free space. A backup is **never** considered successful merely because a
  file exists — integrity verification and periodic test-restores into an isolated DB are required
  before a schema-changing update (runbook §7).
- Migrations: the existing **Alembic** framework (transactional where PostgreSQL supports it). Preserve
  **FORCE RLS** / workspace isolation — never disabled to simplify an update. Irreversible migrations
  document their recovery path (restore from a verified backup); destructive recovery requires explicit
  admin approval and never auto-overwrites newer data with an older backup.

## 6. Release channels & policy

- **Channels:** `stable` (default) and `testing`. The server advertises its channel in `capability`;
  the desktop updater uses channel-specific manifests. Testing never auto-pushes to stable.
- **Policy classes:** optional / recommended / required. Required is reserved for security or genuine
  incompatibility; a required update is still cryptographically verified before install. Read-only
  access is preserved during compatibility restrictions where safe.

## 7. Server-update runbook (operator) — execution steps marked *(deferred)*

1. Announce a maintenance window. 2. **Run pre-update checks** (dashboard) → must be *Ready*.
3. Take a verified backup *(deferred tooling)* and validate it. 4. **Enter maintenance mode**
(writes blocked, reads stay up). 5. Apply the verified server package *(deferred)*. 6. `alembic upgrade
head`. 7. Restart services *(deferred)*. 8. Health + `capability` checks. 9. **Exit maintenance mode**.
10. Confirm the audit trail. Recovery: restore the verified backup; destructive recovery needs explicit
approval.

## 8. Offline / USB updates — **REQUIRES WINDOWS INSTALLATION TESTING**

The USB package (`OneStats-USB-Installation/`) must, on a machine with OneStats already installed, offer
**Update Existing Installation** (detect version + install type; verify package; preserve config, users,
DB connection, approved data, media/research; back up + migrate; never create a second database). The
NSIS installer is `installMode: both`; the detection/preserve/upgrade path and the USB update guide are
**outstanding** and need a real installed build to verify (UP-23, UP-24).

## 9. Audit & security

- `update_event` (append-only, system-wide): component, event, from/to version, channel, outcome, actor,
  non-sensitive diagnostics. **Never** passwords, tokens, signing keys or connection strings.
- Security invariants: HTTPS distribution; signed packages verified against an embedded trusted key; no
  arbitrary executable URLs from ordinary users; no unsigned auto-execution; no RLS bypass; PostgreSQL
  never exposed to the public internet; clients never receive DB admin credentials; **no
  remote-command-execution endpoint** in the ordinary API (privileged maintenance is a separate,
  narrowly-scoped mechanism).

## 10. Decisions requiring approval

- **Hosting** for signed releases (object storage / release host / dedicated update service) — cost.
- **Code-signing certificate** (Windows Authenticode) — paid.
- Final **installer rebuild** to embed the updater plugin (deferred during functional acceptance).
- Any **irreversible migration** or **destructive recovery** operation.
