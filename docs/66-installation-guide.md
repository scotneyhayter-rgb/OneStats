# 66. OneStats — Installation Guide (Windows)

A plain-language guide for installing OneStats on Windows, including from a **USB flash drive**. You do
**not** need to install Python, PostgreSQL, Node.js or any developer tools — the installer handles
everything.

> This guide describes the supported installation experience (deliverable 31 §31.6). Building and signing
> the installer, and testing on clean hardware/USB, are release-engineering and manual-acceptance steps.

## Before you start

- Windows 10 or 11 (64-bit).
- About 500 MB free disk space (more for your data and media).
- The OneStats installer (from the USB drive or your download). Verify it against the published
  **SHA256SUMS.txt** if you want to confirm the file is intact.

## Choose how you are installing

The installer asks which kind of setup you want:

| Path | Choose this when… | What it sets up |
|---|---|---|
| **A — Main computer / server** | This PC holds the data and (optionally) other PCs will connect to it | The app **and a new database** on this computer, plus the background service |
| **B — Additional computer (client)** | The data already lives on another OneStats computer/server | The app only; it **connects to your existing server** |
| **C — Standalone (single computer)** | Just one computer, everything local | The app **and a new local database** |

## Installing from USB

1. Insert the USB drive and open it in File Explorer.
2. Double-click **OneStats-Setup.exe** (or the `.msi`).
3. If Windows shows a SmartScreen prompt (the installer is not yet code-signed), choose **More info →
   Run anyway** (see "Code signing" below).
4. Follow the installer: accept the location, let it install the bundled components (offline — no internet
   needed), and finish. Shortcuts are added to the Start menu and desktop.

## First run — connecting

When OneStats first opens it asks how to connect (you can change this later under **Settings → Server
Connection**):

- **This computer (standalone)** — uses the local backend and database on this PC (paths A and C).
- **Connect to a server** — enter your main OneStats server's address (path B), then **Test connection**
  and **Save & reconnect**.

On a brand-new server/standalone database, the first screen creates the **Super Administrator** using the
one-time setup token the server generated (file `.onestats-setup-token`). A **new standalone database** and
**an existing shared database** are always clearly distinguished — OneStats never silently reuses or
overwrites a database.

## Upgrading

Run the newer installer over your existing installation. Your data is **preserved**: OneStats takes a
**backup before applying any database changes** and migrations only move forward. OneStats **never**
overwrites an existing database without an explicit, verified, recoverable step.

## Repair and uninstall

- **Repair** — re-run the installer and choose Repair (restores app files without touching your data).
- **Uninstall** — Windows **Settings → Apps**, or the installer's Uninstall option. Uninstalling the app
  does **not** delete your database or backups unless you explicitly confirm.

## Code signing (note)

The installers are **not yet code-signed**, so Windows may warn before running them. Code-signing requires
a purchased certificate (a cost decision pending approval). Until then, verify the installer against the
published checksum and proceed with **Run anyway**.

## Getting help

See the release notes (`docs/RELEASE_NOTES.md`) for what's in each version, and the deployment plan
(`docs/31-windows-deployment.md`) for the technical details.
