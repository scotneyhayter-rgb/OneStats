# Phase 15 — Website Publishing & Integration: Implementation Report

**Status: IMPLEMENTED (hosting-neutral core) — AWAITING COMBINED MANUAL ACCEPTANCE (deferred to after
Phase 17).** Not recorded as formally user-accepted. A **hosting decision is required before public
deployment** (see §"Hosting decision required"). No public infrastructure was deployed and no recurring
cost was incurred.

Built on deliverable 29 (§29.6). The architecture deliberately supports **both** (1) static report
publishing to existing website hosting and (2) a future centrally-hosted OneStats publishing service, and
commits to neither.

## What was implemented

- **Durable snapshots (offline-capable).** Publishing a report or a public player profile stores a
  **snapshot** (rendered data + self-contained branded HTML + checksum) on the `publication` row
  (migration 0052). Public access reads the snapshot only — **never the live engine or the database** — so
  it keeps serving the **last successfully published approved snapshot even while the Windows computer is
  offline**.
- **Permanent individual report URLs + saved filters.** Each publication has a permanent, unguessable
  `slug` bound to a report id + saved filters; the URL does not change when the data updates.
- **Public player profiles** — published through the same snapshot, using the **public career view** that
  strips DOB / junior / private data (privacy by construction; tested).
- **Secure read-only JSON feed** — `GET /api/v1/public/r/{slug}.json` (for embedding / third parties).
- **Embeddable HTML** — `GET /api/v1/public/r/{slug}` (and `/p/{slug}` for profiles): a branded,
  self-contained page suitable for linking or `<iframe>` embedding.
- **Static export** — one click downloads a self-contained `{slug}.html` + `{slug}.json` pair to upload to
  existing website hosting (the RMCC site's External URL field) — the zero-recurring-cost path.
- **Publish / unpublish / revoke** — unpublished/revoked slugs stop resolving immediately (tested).
- **Automatic updates after approved-stat changes** — a recompute flags published publications **stale**;
  a refresh (one click, or `POST …/publications/refresh`) regenerates snapshots. Public serving keeps the
  last good snapshot until the refresh succeeds, so the public site never goes dark.
- **Club branding** on every public page (club name + primary colour from workspace branding).
- **Security** — public endpoints are unauthenticated and read-only, serve only `published` snapshots by
  slug via RLS, and expose no admin surface or database. Management is admin-only (`workspace.manage`) and
  workspace-isolated (admin of one workspace cannot see or change another's publications; tested).
- **Desktop** — a Website Publishing admin screen (Club Management → Website Publishing): publish a report,
  list/manage publications, copy the URL, preview, download the static files, refresh, unpublish/revoke. A
  **Publish** button on the Player Profile publishes a public profile.

## RMCC website External URL — investigation (UNVERIFIED)

The RMCC website (a Lovable-built site) exposes an **External URL** field per report category. Such a field
stores a URL the site links to (or embeds). OneStats produces **standard URLs** that fit this field in
either hosting mode:
- **Static export** → upload `{slug}.html` to the club's existing hosting; put that file's URL in the
  External URL field. This is the recommended, no-recurring-cost path.
- **Public edge URL** → the `/public/r/{slug}` URL from a reachable OneStats host (local preview today; a
  future central service for the internet).

**This integration is NOT verified.** It has not been tested against the live RMCC site, which needs site
admin access/credentials and a publicly reachable URL (hence the hosting decision below). Per instruction,
nothing is assumed verified until tested. This is recorded as an external dependency (deliverable 37).

## Hosting decision required before public deployment

The core is hosting-neutral; **public deployment needs one decision** (and no cost is incurred until you
approve):
1. **Static hosting** — publish static files to the club's existing web host (minimal/zero recurring cost;
   the RMCC site serves them). Best first step.
2. **Central OneStats publishing service** — a hosted edge serving `/public/...` for many clubs (ongoing
   paid hosting + ops). Suitable later for multi-club/association use.

Either way, the same snapshots are used. **Do not purchase hosting or deploy public infrastructure without
your approval.**

## Automated test results

- Backend `tests/test_publishing.py` (6): publish a report + serve the snapshot publicly with **no**
  workspace context; unpublish/revoke stop serving; **offline last-good** snapshot + stale→refresh; static
  export produces branded HTML + JSON; **public profile excludes the private DOB**; workspace isolation
  (admin B sees none of A's; the public edge still serves A's published snapshot).
- Desktop `features/publishing/publishing.test.tsx` (1): lists a publication and publishes a report.
- Full suites green; `ruff` + `tsc` clean. (Totals in the commit.)

## Risks & limitations

- **Public reachability** depends on the hosting decision above — the built-in `/public` edge is reachable
  only where the backend is reachable (local preview today).
- **Images/photos** are not yet included in public profile snapshots (serving images publicly needs the
  image files hosted too) — a follow-up with the chosen hosting.
- **Automatic refresh** is flag-driven (stale) + one-click/endpoint refresh; a fully scheduled auto-refresh
  can be wired when a hosting target exists.
- The **RMCC External URL integration is unverified** (above).

## Readiness

Phase 15's hosting-neutral publishing core is complete and tested. Proceeding to **Phase 16 — Mobile
Records Portal** (no consequential decision blocks it; it reads the same publication edge). **No phase is
marked user-accepted; manual acceptance remains deferred to after Phase 17.**
