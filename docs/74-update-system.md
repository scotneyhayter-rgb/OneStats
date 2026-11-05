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
| Desktop app | `apps/desktop/src-tauri/tauri.conf.json` (+ `package.json`, `src/lib/version.ts`) | `1.0.0-beta.2` |
| Server | `services/api/onestats/core/version.py` → `SERVER_VERSION` (`onestats.__version__`) | `1.0.0-beta.2` |
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

## 3. Desktop updater — **IMPLEMENTED IN CODE · AUTOMATED TESTS PASSED (REQUIRES WINDOWS INSTALLATION TESTING + a signed GitHub Release to go live)**

The secure download/verify/install flow uses the **official Tauri 2 updater** (no custom executable
downloader). Hosting is **free GitHub Releases**; signing uses a **free Tauri updater keypair**. No paid
Windows Authenticode certificate is used, so first-run shows a one-time SmartScreen warning (acceptable).

- **IMPLEMENTED IN CODE · AUTOMATED TESTS PASSED:**
  - `tauri-plugin-updater` + `tauri-plugin-process` added to `src-tauri` (`Cargo.toml`), registered in
    `lib.rs` (desktop-only), and permitted in `capabilities/default.json` (`updater:default`,
    `process:allow-restart`). `tauri.conf.json` carries the `plugins.updater` block (`endpoints`,
    trusted `pubkey`, `windows.installMode: passive`) and `bundle.createUpdaterArtifacts: true`.
  - **Updates & Version UI** now drives the real updater when a release service is configured and the
    app runs inside Tauri: check → download (with %) → signature-verify → install → relaunch, with an
    "Install & restart" action and progress/error states. The honest "no update service configured →
    installer" state remains the fallback (browser/dev shell or unconfigured server). It also
    distinguishes an **expired session** (401 → "please sign in again", server not marked unavailable)
    from a genuine server outage (5xx/network). Covered by `updates-version.test.tsx`.
  - **Release-manifest generator** (`scripts/build-release-manifest.py`) emits our rich manifest **and**
    a Tauri `latest.json` with the real GitHub download URL (`--github-repo scotneyhayter-rgb/OneStats`) and the embedded
    updater signature (`--sig-file`/`--signature`); it enforces HTTPS and exits non-zero on an
    unsigned/unhosted manifest so nothing is published silently. Covered by `test_release_manifest.py`.
  - **Release workflow** (`.github/workflows/release.yml`): on a `v*` tag it builds, signs (private key
    from Actions secrets) and uploads the NSIS setup + `latest.json` to a **draft** GitHub Release via
    `tauri-action`.
- **SIGNING — keypair (generated; store the private key):** a free updater keypair has been generated
  with `tauri signer generate`. The **public key is embedded** in `tauri.conf.json` (see §11 for the
  value). The **private key must never be committed**: it lives only in an env var for local signed
  builds (`TAURI_SIGNING_PRIVATE_KEY` = the key string or its file path, plus
  `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`, empty for this key) and in the **GitHub Actions secrets**
  `TAURI_SIGNING_PRIVATE_KEY` / `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` for CI. Losing it means updates can
  no longer be signed. Windows **Authenticode** signing (distinct from the updater signature) stays a
  paid, approval-gated option — not used.
- **HOSTING — GitHub Releases (free):** the updater `endpoints` (desktop) and the server
  `release_manifest_url` default (env `ONESTATS_RELEASE_MANIFEST_URL`) are wired to the official public
  repo **`scotneyhayter-rgb/OneStats`**:
  `https://github.com/scotneyhayter-rgb/OneStats/releases/latest/download/latest.json`. The repo is
  public (private repos need a token the updater can't supply). Publish via the workflow, or manually
  with the `gh` fallback in §11.
- **REQUIRES WINDOWS INSTALLATION TESTING:** download, signature verification, install and restart on a
  real installed build (UP-08..UP-13).

Enabling the updater in a shipped build requires the **one deferred installer rebuild** (per the
development rules — not done here). Everything else is wired so the updater goes live once the private
key is stored, the installer is rebuilt once, and the first signed GitHub Release is published to
`scotneyhayter-rgb/OneStats`. See the §11 go-live checklist.

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

- **Hosting** for signed releases — chosen: **free GitHub Releases** (no recurring cost).
- **Code-signing certificate** (Windows Authenticode) — paid; **not used** (one-time SmartScreen warning accepted).
- Final **installer rebuild** to embed the updater plugin (deferred during functional acceptance — §11 step 3).
- Any **irreversible migration** or **destructive recovery** operation.

## 11. Go-live checklist (desktop in-app updates)

The updater is wired in code (§3). Four human steps remain to make it live:

1. **Store the private signing key (once).** The free updater keypair is already generated; the public
   key is embedded in `tauri.conf.json`. Keep the **private key** somewhere safe (password manager /
   secrets store) — it is printed to you out-of-band and is **never** in the repo. Add two GitHub Actions
   secrets on the release repo: `TAURI_SIGNING_PRIVATE_KEY` (the key string, or the `.key` file
   contents) and `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` (empty for this key). For a local signed build,
   set the same two as environment variables. **If the key is lost, updates can no longer be signed.**

2. **Release repo — already set.** Both spots are wired to the official public repo
   `scotneyhayter-rgb/OneStats`: the desktop updater `endpoints` in
   `apps/desktop/src-tauri/tauri.conf.json`, and the server `release_manifest_url` default in
   `core/config.py` (override with env `ONESTATS_RELEASE_MANIFEST_URL`). Both point at
   `https://github.com/scotneyhayter-rgb/OneStats/releases/latest/download/latest.json`.

3. **Rebuild the installer once (deferred step).** Build the Windows app with the updater plugin and the
   signing env vars set, producing the NSIS `-setup.exe`, its `.sig`, and `latest.json`. This is the one
   installer rebuild deferred during functional acceptance.

4. **Publish the first signed GitHub Release.** Either push a `v*` tag and let
   `.github/workflows/release.yml` build/sign/upload a **draft** release (review, then publish), or do it
   manually:

   ```sh
   # after a signed `tauri build` (dist/release holds latest.json via build-release-manifest.py)
   gh release create v1.0.0-beta.2 \
     "apps/desktop/src-tauri/target/release/bundle/nsis/OneStats_1.0.0-beta.2_x64-setup.exe" \
     "dist/release/latest.json" \
     --repo scotneyhayter-rgb/OneStats --title "OneStats 1.0.0-beta.2" --notes-file docs/RELEASE_NOTES.md
   ```

   Then run **UP-08..UP-13** on a real installed build (download → verify → install → relaunch).

**Embedded updater public key** (safe to commit — it only *verifies* signatures):

```
dW50cnVzdGVkIGNvbW1lbnQ6IG1pbmlzaWduIHB1YmxpYyBrZXk6IDEzMDRDNjY5NzFDMUUwMDAKUldRQTRNRnhhY1lFRXcxeGRGaFJJSW1WbkMvYU0zY05HanBBOXh6WWxUdFlDVm8xSFRRUkFUZksK
```
