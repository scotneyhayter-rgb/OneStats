# OneStats — Release Notes

Versioning is kept in sync across `apps/desktop/package.json`, `apps/desktop/src-tauri/tauri.conf.json`
and `apps/desktop/src/lib/version.ts`. Installer checksums (SHA-256) are published with each build
(`scripts/compute-installer-checksums.ps1`).

## 1.0.0-beta.5 — 2026-11-10

Research, statistics, venues, honours and a redesigned player screen.

**Changed since beta.4:**
- Research Centre: a new **Create scorecard from clipping** action turns OCR'd / transcribed scorecard
  text into a reviewable draft — it suggests existing players to match each name against, and creates no
  players and saves nothing until you confirm. Unknown figures stay blank, never zero. (Batting first;
  bowler/fielder matching and bowling figures to follow.)
- People: a player's screen now also lists clubs they only **played for** (from match appearances, no
  recorded affiliation), separately from recorded affiliations.
- Statistics → Report Catalogue: an opened report now offers the **Club / Team / Season / Competition /
  Grade / Ground** filters it supports (defaulting to your club), feeding both the on-screen figures and
  the PDF/CSV export; opening a report now shows it in a focused, full-width view.
- Teams & Venues: a ground's **Locality, Region, Country, Postcode, Address and Coordinates** are now
  editable (previously only the name). Merging two names of one ground was already available.
- Records: the **Life Members & honorary recognition** list now also shows members recorded as a
  per-person recognition (not only dedicated honour records), each with the player's name.
- People: the player detail screen is redesigned as a **full page** (header band + two-column layout),
  and you can now **affiliate a player to a club** directly from it.

> Installed manually, like beta.4 (self-update is not enabled). The minimum-supported-desktop floor stays
> at `1.0.0-beta.1`.

## 1.0.0-beta.4 — 2026-11-08

Scorecard entry, research gap click-through, and club-scoped profile publishing.

**Changed since beta.3:**
- Manual scorecard entry: the Bowler box now shows only when a bowler is actually part of the entry —
  it is hidden for a not-out batter and for dismissals with no bowler, and switching to one of those
  clears any stale bowler.
- Records & profile: the `min.` badge now has a tooltip explaining it marks a *known minimum* — the real
  figure may be higher where some innings are still unknown (unknown is never treated as zero).
- Website publishing: a published Player Profile can now be **scoped to a single club**, so a club's site
  only shows that club's stats and not figures from a player's other clubs. Published profiles also now
  carry the player's **honour/role badges**.
- Website publishing panel: it no longer presents the internal relative path as if it were a public URL.
  Until central hosting exists it tells you to **download** the profile/report and upload it to your own
  site, with the Copy action reserved for a genuinely public address.
- Research Centre: a season assessed as complete but still flagged incomplete now shows a short
  reconciliation note explaining why, and the gap tiles are **clickable** — they take you straight to the
  affected matches (via a new `?issue=` filter on the match list) instead of making you hunt for them.
- Research Centre overview: each gap row has a **View matches** button that opens the filtered match list.
- People: a player's **Club & team affiliations** now shows the club on each row (club · role — years).

> Installed manually, like beta.3 (self-update is not enabled). The minimum-supported-desktop floor stays
> at `1.0.0-beta.1`.

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
