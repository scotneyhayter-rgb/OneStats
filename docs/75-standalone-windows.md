# 75. Standalone Windows Desktop Installation

**Created 2026-10-27.** How OneStats runs as a normal, self-starting Windows desktop application on a
single PC: double-click the icon → the app opens, starts its own backend, connects to the local
database, and you log in — **no Claude Code, no terminal, no manual Python/FastAPI/PostgreSQL**.

> **Status honesty.** Tags: **IMPLEMENTED** (code), **VERIFIED (DEV)** (proven in this environment),
> **REQUIRES WINDOWS INSTALL TEST** (only confirmable on the installed build). Nothing is marked
> acceptance-passed.

## 1. Architecture

OneStats is three cooperating parts. The standalone build makes the app own the lifecycle of the other two:

1. **Desktop app** (Tauri) — the window you see.
2. **Backend** (FastAPI) — packaged as a single **sidecar executable** `onestats-server.exe` (PyInstaller),
   launched by the app on startup and stopped on exit. Binds **127.0.0.1 only** (never the network).
3. **PostgreSQL** — the database.

**This PC (the immediate priority):** PostgreSQL 17 is already installed and running as the auto-starting
Windows service `postgresql-x64-17`, and your `onestats` database already holds all your work. The
standalone build **reuses that existing service and database**, so **all existing data is preserved
automatically** — there is nothing to migrate and no second database is created. Bundling a second
PostgreSQL would be redundant and risky here; that is only needed for *fresh* PCs (deferred).

**Startup sequence** (handled by `onestats/standalone/launcher.py` inside the sidecar):
resolve the per-user data dir → load config → wait for the local PostgreSQL → `alembic upgrade head`
(forward-only, idempotent, non-destructive) → serve on loopback. The app shows "Starting OneStats…"
and polls `/health` (up to 45s) before showing the UI, so the brief backend start-up is invisible.

## 2. What is implemented & verified

| Piece | Status |
|---|---|
| Self-starting backend orchestration (`standalone/launcher.py`) | **VERIFIED (DEV)** — connects, migrates, serves on loopback; logs to `%LOCALAPPDATA%\OneStats\logs\server.log` |
| Packaged backend `onestats-server.exe` (PyInstaller) | **VERIFIED (DEV)** — 55 MB; started from a neutral folder, reached the DB, migrated, served `/health` 200 |
| Per-user config seeding (`scripts/prepare-standalone-config.py`) | **VERIFIED (DEV)** — writes `%LOCALAPPDATA%\OneStats\onestats.env` from the dev `.env`; data preserved |
| Tauri sidecar wiring (`lib.rs`, `tauri.conf.json`, capability) | **IMPLEMENTED** — spawn on startup, pipe logs, kill on exit; built into the installer |
| App startup health-wait | **VERIFIED (DEV)** — "Starting OneStats…" until the backend answers |
| Local backups (`domain/backups.py`, System Updates UI, `scripts/onestats-backup.py`) | **IMPLEMENTED** — create/verify/list via the app; restore via CLI (destructive, `--confirm`) |
| Standalone installer (NSIS, with the sidecar bundled) | **REQUIRES WINDOWS INSTALL TEST** — produced by `tauri build`; install/run must be confirmed on Windows |

## 3. Data preservation

Because the standalone build uses the **same** PostgreSQL service and `onestats` database you have been
using, your workspaces, matches, people, scorecards, statistics, publications, themes, settings and
media are all retained as-is. The launcher only runs `alembic upgrade head`, which moves the schema
**forward** and never drops or overwrites data. Before any schema-changing update, take a backup (§5).
No blank replacement database is ever created.

## 4. Building the standalone release candidate

From a dev checkout on the target PC:

```bash
# 1. Seed the per-user config (one-time; copies the local DB connection from the dev .env)
python scripts/prepare-standalone-config.py

# 2. Package the backend into a single exe
cd services/api && ./.venv/Scripts/python -m PyInstaller onestats-server.spec --noconfirm

# 3. Place it where Tauri bundles it as the sidecar
cp dist/onestats-server.exe ../../apps/desktop/src-tauri/binaries/onestats-server-x86_64-pc-windows-msvc.exe

# 4. Build the installer (NSIS; MSI is skipped because the version has a pre-release tag)
cd ../../apps/desktop && npm run tauri build -- --bundles nsis
```

Output installer: `apps/desktop/src-tauri/target/release/bundle/nsis/OneStats_1.0.0-beta.1_x64-setup.exe`.
It is **not code-signed** (paid certificate still pending), so Windows SmartScreen shows
"Windows protected your PC" → **More info → Run anyway**.

## 5. Backups & restore

- **In-app** (Super Admin → System Updates → *Create backup now*): a verified custom-format dump in the
  backup directory (`%LOCALAPPDATA%\OneStats\backups`, outside anything the uninstaller removes).
- **Restore** is intentionally CLI-only (destructive): `python scripts/onestats-backup.py restore <file> --confirm`.
- **Superuser requirement:** the database is FORCE-RLS protected, so a *complete* backup needs a
  PostgreSQL **superuser** (or a BYPASSRLS role). Set `ONESTATS_PG_SUPERUSER_PASSWORD` (and optionally
  `ONESTATS_PG_SUPERUSER`, default `postgres`) in `%LOCALAPPDATA%\OneStats\onestats.env`. Without it,
  backup reports a clear message and writes nothing — it never produces a partial/misleading dump.

## 6. Daily operation

Double-click the OneStats desktop icon → the app starts the backend sidecar → connects to the local DB
→ you log in. Works offline for all local features (external connectors fail gracefully). Closing the
app stops the sidecar. A Windows restart does not break the install (PostgreSQL is an auto-start
service; the app restarts the sidecar each launch) — **REQUIRES WINDOWS INSTALL TEST**.

## 7. Real-device acceptance (ST-01..ST-15)

Added to the acceptance register ([62](62-deferred-acceptance-register.md)). ST tests that exercise the
installed experience (install, shortcut, auto-start, restart, offline, backup on the installed build)
can only be confirmed on your Windows machine and are **not** marked passed here.

## 8. Known limitations / outstanding

- **Installer install/run not yet tested on a real Windows session** (ST-01..15). The sidecar wiring and
  config are built in; the installed behaviour must be confirmed by you.
- **No code signing** (paid certificate decision pending) → SmartScreen warning.
- **Fresh-PC bundling of PostgreSQL** (initdb a private cluster, bundle the binaries) is **deferred** —
  not needed on this PC, which already has PostgreSQL 17. Required before shipping to machines without it.
- **Automatic updates** are not operational (signing/hosting pending, docs/74); use the offline
  installer-based update path for now (run a newer installer over the existing install).
- A **first-run GUI wizard** for a brand-new database (no existing data) is not built; on this PC it is
  unnecessary because the database already exists. Needed for fresh-PC installs.
