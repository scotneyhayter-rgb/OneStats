# Phase 17 — Windows, Website & Mobile Release: Implementation Report

**Status: IMPLEMENTED (app-level release engineering + installer configuration & artifacts) — AWAITING
COMBINED MANUAL ACCEPTANCE (deferred, now due: this is the last development phase before acceptance).**
Not recorded as formally user-accepted.

Phase 17 hardens and packages OneStats for release (deliverable 31 §31.6). The parts that are **software**
are built and tested; the parts that are **build/release-engineering or real-hardware** (actually building,
signing and USB-testing the installer) are prepared and documented, and the **code-signing certificate is a
paid decision flagged for your approval** — nothing was purchased.

## What was implemented (buildable + tested)

- **Runtime connection configuration (the three install paths, at the app level).** The backend URL is now
  runtime-configurable (`getApiBase`/`setApiBase`), so one build serves **standalone**, **main server** and
  **additional-client** installs without rebuilding. A **Connection** panel (Settings, and on the
  "backend unreachable" first-run screen) lets the user choose **This computer (standalone)** or **Connect
  to a server**, **test** the connection (`/api/v1/health`), and **save & reconnect**. A new standalone
  database vs an existing shared database stays clearly distinguished (the Super-Admin setup-token flow
  already separates a fresh DB from a connect-to-existing one).
- **Windows installer bundle configuration** (`src-tauri/tauri.conf.json`): NSIS + MSI targets,
  **offline WebView2** (`offlineInstaller`, for USB/offline installs), per-machine **or** per-user install
  mode, installer icon, publisher/description metadata, Start-menu/desktop shortcuts.
- **Versioning & About**: a single version source (`lib/version.ts`) synced to `package.json` and
  `tauri.conf.json` (**1.0.0-beta.1**), shown in the app's About/Sidebar.
- **Installer checksums**: `scripts/compute-installer-checksums.ps1` generates `SHA256SUMS.txt` for built
  installers.
- **Release notes** (`docs/RELEASE_NOTES.md`) and a **user-friendly installation guide**
  (`docs/66-installation-guide.md`) covering paths A/B/C, USB install, first-run, upgrade, repair, uninstall.
- **Upgrade safety (policy + mechanics)**: migrations are forward-only (Alembic); the documented upgrade
  flow takes a **backup before any database change** and **never overwrites an existing database** without
  an explicit, verified, recoverable step (deliverable 32 backup/manifest is the backing mechanism).

## What is build-time / real-hardware (prepared & documented, NOT executed here)

These require a Windows build machine with the Tauri/Rust toolchain and real hardware/USB, so they are
release-engineering and **manual acceptance** items — not run in this environment, and not claimed as done:

- **Actually building** the `.exe`/`.msi` with `tauri build` (and packaging the FastAPI backend sidecar +
  the database engine so no manual Python/PostgreSQL/Node install is needed — the §31.3a packaged-sidecar
  design is the plan).
- **Code-signing** the installers — needs a **purchased certificate** (a recurring cost). **Decision
  required**; until approved, installers are unsigned and Windows SmartScreen will warn (documented).
- **Testing**: clean install on a supported Windows PC, install **from USB**, **additional-client** install
  against a server, **upgrade** (data preserved), and **repair/uninstall** — all manual acceptance (PUB/
  install tests in the register).

## Automated test results

- Desktop `features/settings/connection-settings.test.tsx`: standalone vs connect-to-server, URL field,
  save gating.
- `tauri.conf.json` validated as JSON; version synced across the three sources.
- Full suites green; `ruff` + `tsc` clean. (Totals in the commit.)

## Decisions required before public/production release

1. **Public hosting** (Phase 15/16) — static hosting vs a central OneStats service (paid). No cost without
   approval.
2. **Code-signing certificate** (this phase) — purchase a certificate to sign installers (cost). No
   purchase without approval.

## Readiness

Phase 17's software deliverables are complete and tested; the installer **build/sign/USB-test** steps are
prepared and documented for a Windows build machine, pending the two decisions above. **This is the last
development phase before acceptance.** Next: assemble and present the **consolidated manual acceptance
programme** (deliverable 62). **No phase is marked user-accepted.**
