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

## Phase 17 — Windows Install, Website & Mobile Release (IMPLEMENTED 2026-10-26 — see [67](67-phase17-report.md))

App-level release engineering is built & tested; the installer build/sign/USB tests are manual/hardware.

| # | Test | Where / How | Expected |
|---|---|---|---|
| INS1 | Connection config | Settings → Server Connection (or first-run) | Choose standalone vs server; test; save & reconnect |
| INS2 | Version/About | Settings → About / Sidebar | Shows version 1.0.0-beta.1 |
| INS3 | Clean install | Install on a supported Windows PC | App + bundled components; shortcuts; no manual Python/PG/Node *(manual/hardware)* |
| INS4 | USB install | Install from a USB drive (offline) | Installs offline *(manual/hardware)* |
| INS5 | Additional client | Install, choose Connect to a server | Connects to the existing server *(manual/hardware)* |
| INS6 | Upgrade | Install a newer version over an old one | Data preserved; backup taken first; no DB overwrite *(manual/hardware)* |
| INS7 | Repair / uninstall | Installer repair + Windows uninstall | Repairs app files; uninstall keeps data unless confirmed *(manual/hardware)* |
| INS8 | Checksums | Run compute-installer-checksums.ps1 | SHA256SUMS.txt matches the installers |
| INS9 | Signing | Inspect installer signature | **Pending the code-signing certificate decision (paid)** |

Automated coverage: `features/settings/connection-settings.test.tsx`; `tauri.conf.json` validity + version
sync. **Decisions required:** public hosting (static vs central) and code-signing certificate (both paid;
no cost without approval).

## User Management & First-Login Security (IMPLEMENTED 2026-10-26 — see [68](68-user-management-report.md))

Super-Admin user management + secure first-login (deliverable 31 §31.7). Manual acceptance (DEFERRED):

| # | Test | Where / How | Expected |
|---|---|---|---|
| USR1 | User Management screen | Settings → User Management (Super Admin) | List/create/edit users; gated for non-super-admins |
| USR2 | Create + temp password | Create a user | A one-time temporary password is shown; login forces a change |
| USR3 | First-login change | Sign in with a temp password | Forced change-password screen before anything loads |
| USR4 | Invitation | Invite a user; accept the token | Account activates on setting a password; single-use; revocable |
| USR5 | Suspend / reactivate | Toggle a user's status | Suspended users can't sign in; sessions revoked |
| USR6 | Reset password | Reset a user's password | New temp password; old sessions revoked |
| USR7 | Roles | Assign workspace roles; promote/demote Super Admin | Backend-enforced; a Club Admin can't grant Super Admin |
| USR8 | Last-admin guard | Try to suspend/demote the only Super Admin | Blocked |
| USR9 | Rate limiting | Repeated failed logins | Temporarily blocked; a success resets |
| USR10 | Audit history | View a user's history | Login attempts + admin actions listed |
| USR11 | Recovery | Operator issues a recovery token → recover | Super Admin restored; forced change; token single-use; can't be done remotely |
| USR12 | Connect-to-server first run | Additional client → Connect to a server | Validates connection; no new DB; loads only authorised workspaces |

Automated coverage: `tests/test_user_management.py` (9); `features/admin/user-management.test.tsx` (2);
`features/settings/connection-settings.test.tsx` (1). Backend enforcement, Argon2id, single-use/expiring
temp + recovery tokens, rate limiting, escalation + last-admin guards.

## Workspace API & Integrations Management (IMPLEMENTED 2026-10-26 — see [70](70-api-integrations.md))

Clubs manage their own external-provider API credentials from **Workspace Settings → API & Integrations**
(no config-file/source edits). Manual acceptance (DEFERRED):

| # | Test | Where / How | Expected |
|---|---|---|---|
| INT1 | Open the screen | Settings → API & Integrations (admin) | Lists supported providers with status; gated for non-admins |
| INT2 | Add a credential | Add PlayHQ API key + org id + tenant | Saved; shown *Configured*; secret never displayed (password field; "stored securely") |
| INT3 | Test connectivity | Click Test connection | Real authenticated request; *Connected* only on genuine success; failure shows a sanitised message (no secret) |
| INT4 | Enable / disable | Toggle the integration | Disabled credential cannot be used by sync; re-enable restores it |
| INT5 | Rotate secret | Rotate → enter a new secret | Secret replaced; old one no longer used; still never displayed |
| INT6 | Revoke | Revoke the credential | Stored secret destroyed; status *Revoked*; unusable |
| INT7 | Audit history | View Integration activity | create / test / rotate / revoke listed; no secret values |
| INT8 | Workspace isolation | As another workspace / admin | Cannot see or use the first workspace's credentials; same provider can hold different creds per workspace |
| INT9 | Permissions | As a non-admin (Viewer) | No access to credential management (backend-enforced `import.configure`) |
| INT10 | SSRF protection | Custom API with an internal URL (e.g. `https://127.0.0.1`, `169.254.169.254`) | Rejected; cannot reach internal networks |
| INT11 | Sync uses the stored credential | Configure PlayHQ here → AutoSync | The run authenticates with the **workspace's** credential; imported matches stay draft |
| INT12 | Backup/restore safety | Inspect a DB backup | Secrets are ciphertext; useless without the separately-held encryption key |

Automated coverage: `tests/test_integrations.py` (28), `features/settings/integrations.test.tsx` (3).
**INT3/INT11 for PlayHQ remain gated** on a valid API key + live cricket-v2 field validation (see
[69](69-playhq-connector.md), [70](70-api-integrations.md)).

## THE CONSOLIDATED ACCEPTANCE PROGRAMME (assembled 2026-10-26, after Phase 17)

All development through Phase 17 is complete. The outstanding **manual** tests are organised below into one
programme, de-duplicated, with complete requirement coverage. Each area maps to the concrete, numbered test
blocks above (run those rows); cross-cutting areas add the extra checks listed.

| # | Area | Run these | Extra cross-cutting checks |
|---|---|---|---|
| 1 | End-to-end workflows | A full create→enter→approve→report→publish pass | Each major workflow start-to-finish in the sandbox |
| 2 | Statistics & report accuracy | Phase 12 (28) + Report Catalogue **RC1–RC15** + spot-checks **A1–A5** | 79-report catalogue, mixed-over-length economy, multi-keeper, forfeits |
| 3 | Player profiles, records & awards | Phase 13 (22) + Player Profiles **P1–P16** | Charts, Grand Finals, honours vs calculated |
| 4 | Historical research & provenance | Phase 10 acceptance ([55](55-phase10-acceptance.md)) | Evidence never overwrites approved stats |
| 5 | Media archive & OneVault | Phase 11 (20) | OneVault must show **unavailable** |
| 6 | Ask OneStats (AI assistant) | **ASK1–ASK7** | No fabrication; deterministic; permission-scoped |
| 7 | Website publishing & public URLs | **PUB1–PUB10** | RMCC External-URL (hosting-gated); privacy |
| 8 | Mobile portal | **MOB1–MOB8** | Responsive on a real phone; read-only |
| 9 | Windows install / upgrade / uninstall | **INS1–INS9** | USB install; upgrade preserves data; signing decision |
| 10 | Backup, restoration & disaster recovery | Phase 11 test 18 + a full restore drill | Pre-upgrade backup; recover from a backup |
| 11 | Permissions, security & workspace isolation | Phase isolation checks + a cross-workspace pass + **INT8–INT10, INT12** | DB-level RLS (automated suite green); role-scoped views; encrypted credentials; SSRF guard |
| 11a | API & Integrations management | **INT1–INT12** | Self-service credentials; secrets never shown; test-before-trust; audited |
| 12 | Accessibility & UX | Keyboard, focus, contrast, scaling across key screens | WCAG AA target |
| 13 | Performance & stability | Association-scale report + large PDF + repeated use | Startup/shutdown; reconnect; interrupted-op recovery |

**Blocking decisions before public/production release** (both paid; no cost without user approval):
public **hosting** (static vs central service), and the **code-signing certificate**.

**External dependencies** (not application defects): OneVault API (unverified); **PlayHQ connector now
implemented** (status `needs_credentials`) — pending the **API key** and **live cricket-v2 response
validation** (see [69](69-playhq-connector.md)); other online connectors gated; RMCC External-URL
integration (unverified). Provider credentials are now **self-service** per workspace via
**Settings → API & Integrations** (encrypted at rest, test-before-trust, audited — see
[70](70-api-integrations.md)); no config-file or source edits are needed to enter them.

**PlayHQ acceptance (deferred):** enter the API key → AutoSync a PlayHQ season in review mode → verify the
imported fixtures/results map correctly (field mapping validated against live responses) → approve → stats
update. Until the key + validation, the connector reports `needs_credentials` and never fabricates data.

## Maintenance

Each phase's completion report updated this register (planned tests → concrete numbered rows). This register
is the single source of truth for what the user will manually verify. **No phase is user-accepted until the
user approves it.**
