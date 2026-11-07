# OneStats — Release Notes

Versioning is kept in sync across `apps/desktop/package.json`, `apps/desktop/src-tauri/tauri.conf.json`
and `apps/desktop/src/lib/version.ts`. Installer checksums (SHA-256) are published with each build
(`scripts/compute-installer-checksums.ps1`).

## 1.0.0-beta.3 — 2026-11-08

Research Centre OCR and manual scorecard-entry fixes.

**Changed since beta.2:**
- Research Centre OCR now actually extracts text: fixes a silent failure on phone-camera (MPO) and other
  non-RGB images, and preprocesses faded newspaper scans (grayscale, upscale, autocontrast, sharpen).
- Manual scorecard entry: clearing a player (the ✕) or blanking a figure back to unknown now persists —
  the batting/bowling/fall-of-wicket/partnership update paths no longer drop an explicit null, so a field
  can be un-set, not only set.
- Batting grid: you can now Tab across a row even after selecting a player — the player picker no longer
  strands focus when it closes, and Tab inside it confirms the highlighted player and moves to the next cell.
- Batting grid: a fresh, editable card opens a full XI (11 positions) ready for input.
- Batting grid: the Fielder box now shows only for fielding dismissals (caught, caught behind, stumped,
  run out); it is hidden for bowled/lbw/hit wicket/caught & bowled, and switching to one of those clears
  any stale fielder.

> Installed manually, like beta.2 (self-update is not enabled). The minimum-supported-desktop floor stays
> at `1.0.0-beta.1`.

## 1.0.0-beta.2 — 2026-11-05

First **updater-capable** build. Adds in-app automatic updates via the official Tauri 2 updater,
with signed releases hosted free on GitHub Releases (check → download → signature-verify against the
embedded public key → install → relaunch). See `docs/74-update-system.md`.

**Changed since beta.1:**
- In-app "Check for updates" now drives the real Tauri updater when a release service is configured and
  the app is running inside the Tauri runtime; it still falls back honestly to the installer-based state
  otherwise.
- Release-manifest generator (`scripts/build-release-manifest.py`) produces the Tauri `latest.json` and a
  rich manifest; an unsigned/unhosted run is flagged (non-zero exit) so nothing can be published silently.

> Note: self-update only works on builds that already ship **with** the updater plugin, so beta.2 must be
> installed manually (the in-app button cannot bootstrap itself onto a beta.1 install). Existing beta.1
> users are not forced to update — the minimum-supported-desktop floor stays at `1.0.0-beta.1`.

## 1.0.0-beta.1 — 2026-10-26 (pre-acceptance release candidate)

First packaged release candidate. Feature-complete through Phase 16; manual acceptance is scheduled after
Phase 17. **Not production-ready until acceptance testing passes.**

**Included (Phases 1–16):**
- Workspaces, onboarding, roles/permissions, database-level workspace isolation (FORCE RLS).
- Clubs/associations, competitions/grades/seasons, playing conditions; teams & venues.
- People & profiles (merge-aware), scorecard entry, verification & data-integrity rules.
- Cricket Statz / universal import; online match discovery (gated); Research Centre.
- Media Archive (OneVault capability-detected, not operational).
- Statistics & Reporting engine (the one deterministic engine), the **79-report Report Catalogue**,
  Records/rankings/achievements, Player Profiles with charts & Grand Finals.
- **Ask OneStats** (deterministic NL → report; no LLM).
- **Website Publishing** (permanent public URLs, JSON feeds, embeds, static export, publish/unpublish/
  revoke, auto-refresh) and the **Mobile Records Portal** (responsive, read-only, snapshot-based).
- **Phase 17 release engineering:** runtime connection configuration (standalone / connect-to-server),
  Windows installer bundle config (offline WebView2, per-machine/per-user NSIS + MSI), version/About,
  installer checksum tooling, and the installation guide.

**Statistical-integrity corrections in this cycle:** career economy across mixed over lengths (true overs
per match), multiple-wicketkeeper attribution, best-bowling-in-a-match runs tie-break, approved forfeit
policy, and merge-aware aggregation.

**Known limitations / decisions pending:**
- **Public hosting decision** (static hosting vs a central service) required before public deployment.
- **Code-signing certificate** is a paid decision (installers are unsigned until approved).
- OneVault external API unverified; PlayHQ/online connectors gated; RMCC External-URL integration
  unverified. Combined manual acceptance deferred to after Phase 17.
