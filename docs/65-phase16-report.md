# Phase 16 — Mobile Records Portal: Implementation Report

**Status: IMPLEMENTED (public read-only portal) — AWAITING COMBINED MANUAL ACCEPTANCE (deferred to after
Phase 17).** Not recorded as formally user-accepted.

Built on deliverable 30, reusing the Phase 15 publication edge. The portal is **responsive, read-only, and
snapshot-based** — it reads the published publication cache, never the administrative database, so it works
independently of server uptime and exposes no admin surface or private data.

## What was implemented

- **Public mobile records portal** — `GET /api/v1/public/club/{workspace_id}`: a mobile-first, club-branded,
  **responsive** index page listing the club's published **players** and **reports**, with an instant
  client-side **search** filter. Each item links to its published snapshot page (`/public/r|p/{slug}`).
- **Portal JSON** — `GET /api/v1/public/club/{workspace_id}.json` for app/third-party consumption.
- **Snapshot-based & privacy-safe** — the portal lists only `published` publications (approved data; public
  player profiles already exclude DOB/junior/private, Phase 15). Unpublished/revoked items never appear.
  No workspace context is needed to serve it (RLS exposes published rows), and it never touches the live
  engine or admin DB.
- **Branding** — club name and primary colour come from the stored snapshots (no DB read required).
- **Desktop** — an "Open portal" action on the Website Publishing screen opens the club portal.

## Scope notes (deliverable 30)

- The **core public read-only records portal** is delivered here (mobile-first, branded, searchable,
  snapshot-based). It reuses the exact publication edge, so it shares Phase 15's hosting path — the same
  **hosting decision** (static vs central service) governs public reachability; local preview works today.
- **Authenticated member extras** (permission-scoped read-only API for additional non-public data) and the
  **Ask OneStats-on-portal** read-only surface are available conceptually via the existing authenticated
  API and the deterministic Ask engine; a dedicated authenticated portal app is a follow-up once a hosting
  target exists. Documented, not over-claimed.
- **Mobile media upload** (deliverable 20a, the permissioned write path) is a separate, authenticated flow
  tracked with Phase 11 media; not part of this public read-only portal.

## Automated test results

- Backend `tests/test_publishing.py::test_mobile_portal_lists_published_only`: the portal lists published
  items with no workspace context, excludes unpublished/revoked, carries club branding, and renders a
  responsive (viewport) HTML index.
- Full suites green; `ruff` + `tsc` clean. (Totals in the commit.)

## Risks & limitations

- **Public reachability** depends on the Phase 15 hosting decision (static vs central service); the portal
  is reachable where the backend/public edge is reachable (local preview today).
- A **polished standalone portal app** (`apps/portal/`) and an **authenticated member view** are follow-ups
  tied to the hosting target; the responsive branded index + snapshot pages are delivered now.
- Accessibility targets WCAG AA by construction (semantic HTML, large tap targets, viewport, contrast via
  branding); a formal audit is a manual acceptance item.

## Readiness

The public mobile records portal is implemented and tested. Proceeding to **Phase 17 — Windows, Website &
Mobile Release** (the mandatory production installer & USB distribution, §31.6). **No phase is marked
user-accepted; manual acceptance remains deferred to after Phase 17.**
