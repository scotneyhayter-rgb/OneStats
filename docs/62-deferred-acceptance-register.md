# 62. Deferred Manual Acceptance Register

**Created 2026-10-26.** By user decision, combined **manual** acceptance testing is **deferred until after
Phase 17**. This register preserves every deferred manual test and grows as Phases 14–17 are built. After
Phase 17 these are consolidated into one organised acceptance programme (de-duplicated, full coverage).

> **No phase is formally user-accepted until the user approves it.** Automated tests passing is development
> assurance, not acceptance. This register tracks the **hands-on** tests the user will run.

## Status legend

`PENDING` — awaiting the user's manual run · `DEFERRED` — intentionally postponed to the post-17 programme.
All rows below are currently **DEFERRED** (scheduling), to be run in the consolidated programme.

## Phases 11–13 (already specified) — preserved verbatim

The full detail lives in [60-combined-acceptance-phase11-13.md](60-combined-acceptance-phase11-13.md). It
is preserved unchanged and carried forward:

| Block | Tests | Source |
|---|---|---|
| Phase 11 — Media Archive & OneVault | 20 (incl. OneVault capability-detection must show *unavailable*) | 60 / [57](57-phase11-acceptance.md) |
| Phase 12 — Statistics & Reporting | 28 | 60 |
| Phase 12 — Report Catalogue | 15 (**RC1–RC15**) | 60 |
| Phase 13 — Records, Rankings & Achievements | 22 | 60 |
| Phase 13 — Player Profiles | 16 (**P1–P16**) | 60 |
| Pre-acceptance audit spot-checks | 5 (**A1–A5**: PDF orientation, captaincy populated, profile PDF, mixed-over-length economy, multi-keeper) | 60 |
| **Subtotal (Phases 11–13)** | **106** | |

## Phase 14 — Ask OneStats (IMPLEMENTED 2026-10-26 — see [63](63-phase14-report.md))

Manual acceptance tests (DEFERRED to the post-17 programme):

| # | Test | Where / How | Expected |
|---|---|---|---|
| ASK1 | Natural-language query | Ask OneStats → "Who has scored the most runs?" | Maps to Most Runs; the No. 1 and ranking from the engine; interpretation shown |
| ASK2 | Scope from language | "Who has the most wickets in grand finals?" | Grand-Final filter applied; figures differ from all-matches |
| ASK3 | Captaincy query | "Which captain has the best winning percentage?" | Maps to captaincy win % (min-eligible qualification noted) |
| ASK4 | Qualifications shown | Any answer | Approved-only + known-minimum caveats travel with the answer |
| ASK5 | No fabrication | Ask an unanswerable question | "Couldn't map" + nearest reports; never a guessed number |
| ASK6 | Permissions/scope | As a Viewer / across workspaces | Only permitted, in-workspace data; no cross-workspace leakage |
| ASK7 | Reproducible | Ask the same question twice | Same report spec → same result |

Automated coverage: `tests/test_ask.py` (7), `features/ask/ask.test.tsx` (2).

## Phase 15 — Website Publishing & Public Report URLs (IMPLEMENTED 2026-10-26 — see [64](64-phase15-report.md))

Manual acceptance tests (DEFERRED). Several require a **hosting decision** + reachable URL (see 64):

| # | Test | Where / How | Expected |
|---|---|---|---|
| PUB1 | Publish a report | Club Management → Website Publishing → publish | Permanent public URL created; snapshot stored |
| PUB2 | Public render | Open the public URL (preview) | Correct, **filtered, club-branded** report; no admin/DB surface |
| PUB3 | JSON feed | Open `/public/r/<slug>.json` | Same figures as the report |
| PUB4 | Static export | Download static files | Self-contained HTML + JSON to upload to web hosting |
| PUB5 | RMCC External URL | Paste the URL into the RMCC site's External URL field | Resolves/embeds correctly (**UNVERIFIED** — needs hosting + site access) |
| PUB6 | Auto-update | Approve a stat change → Refresh | Published snapshot updates; public kept serving last-good meanwhile |
| PUB7 | Unpublish / revoke | Toggle status | URL stops resolving |
| PUB8 | Public player profile | Publish a profile | Public profile with **DOB/junior/private excluded** |
| PUB9 | Offline | Stop the backend after publishing | Last-good snapshot still served from the host (no DB dependency) |
| PUB10 | Permissions/isolation | As a non-admin / another workspace | Non-admins can't manage; no cross-workspace publications |

Automated coverage: `tests/test_publishing.py` (6), `features/publishing/publishing.test.tsx` (1).
**Hosting decision required before public deployment** (static hosting vs central service) — see 64.

## Phase 16 — Mobile Records Portal (IMPLEMENTED 2026-10-26 — see [65](65-phase16-report.md))

Manual acceptance tests (DEFERRED; some need the hosting target + a phone):

| # | Test | Where / How | Expected |
|---|---|---|---|
| MOB1 | Portal renders | Open `/public/club/<workspace_id>` (Publishing → Open portal) | Mobile-first, club-branded index of published players + reports |
| MOB2 | On a phone | Open the portal URL on a phone | Responsive layout, large tap targets, readable; no horizontal scroll |
| MOB3 | Search | Type in the search box | Instant client-side filter of players/reports |
| MOB4 | Read-only | Try to act | No write/admin actions; links only open published snapshots |
| MOB5 | Privacy | Inspect a public profile from the portal | No DOB/junior/private; approved data only |
| MOB6 | Published-only | Unpublish/revoke an item | It disappears from the portal |
| MOB7 | Offline/snapshot | Stop the backend after publishing (hosting-dependent) | Portal + snapshots still served from the host |
| MOB8 | Accessibility | Keyboard + contrast check | WCAG AA (semantic HTML, focus, contrast) |

Automated coverage: `tests/test_publishing.py::test_mobile_portal_lists_published_only`.
Reachability shares the **Phase 15 hosting decision**. Authenticated member view + Ask-on-portal + mobile
media upload are follow-ups (see 65).

## Phase 17 — Windows Install, Website & Mobile Release (added as built)

Planned manual tests (deliverable 31 §31.6): clean install on a supported Windows machine; install **from
USB**; **additional-client** install against an existing server; **upgrade** preserving user data; **repair**
and **uninstall**; dependency management (no manual Python/PostgreSQL/Node install); guided first-run
(paths A/B/C); secure server-connection config; installer **checksums** verified; release notes present;
**never** overwrites an existing database without an explicit, verified, recoverable migration.

## Post-Phase-17 consolidated acceptance programme (to assemble)

One organised programme combining all of the above plus cross-cutting suites, de-duplicated with complete
requirement coverage:

- End-to-end workflows across the complete application.
- Statistics & report accuracy (incl. the 79-report catalogue, mixed-over-length economy, multi-keeper).
- Player profiles, records & awards.
- Historical research & source provenance.
- Media archive & OneVault integration.
- Ask OneStats (AI Research Assistant) behaviour.
- Website publishing & public report URLs.
- Mobile portal.
- Windows installation, upgrade & uninstall (incl. USB).
- Backup, restoration & disaster recovery.
- Permissions, security & workspace isolation.
- Accessibility & user experience.
- Performance & stability.

## Maintenance

Each phase's completion report updates this register (its planned tests become concrete, numbered rows).
The register is the single source of truth for what the user will manually verify after Phase 17.
