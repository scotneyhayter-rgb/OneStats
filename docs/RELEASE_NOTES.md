# OneStats — Release Notes

Versioning is kept in sync across `apps/desktop/package.json`, `apps/desktop/src-tauri/tauri.conf.json`
and `apps/desktop/src/lib/version.ts`. Installer checksums (SHA-256) are published with each build
(`scripts/compute-installer-checksums.ps1`).

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
