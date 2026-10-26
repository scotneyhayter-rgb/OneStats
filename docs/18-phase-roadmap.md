# 18-Phase Development Roadmap

**Supporting document** (§31) · referenced by deliverables 1, 35, 37

The 18 phases with purpose, dependencies, key risks and sensible overlap. Phase 1 is this
documentation set. **No phase after 1 starts without user approval.**

## Dependency overview

```mermaid
flowchart TB
  P1["1 Planning & Architecture"] --> P2["2 Desktop & Server Foundation"]
  P2 --> P3["3 Workspaces, Onboarding & Permissions"]
  P3 --> P4["4 Clubs, Associations & Competitions"]
  P4 --> P5["5 People & Profiles"]
  P5 --> P6["6 Matches & Scorecard Entry"]
  P6 --> P7["7 Validation, Verification & Data Integrity"]
  P7 --> P8["8 Cricket Statz & Third-Party Import"]
  P8 --> P9["9 Online Match Discovery"]
  P7 --> P10["10 Research Centre"]
  P6 --> P11["11 Media Archive & OneVault"]
  P7 --> P12["12 Statistics & Reporting Engine"]
  P12 --> P13["13 Records, Rankings & Achievements"]
  P12 --> P14["14 Ask OneStats"]
  P13 --> P15["15 Website Publishing & Sync"]
  P15 --> P16["16 Mobile Records Portal"]
  P15 --> P17["17 Windows, Website & Mobile Release"]
  P16 --> P17
  P17 --> P18["18 RMCC Full-Season Trial"]
```

## Phases

| # | Phase | Purpose | Depends on | Key risks |
|--:|---|---|---|---|
| 1 | Planning & Architecture | This doc set | — | Scope creep; unverified external facts |
| 2 | Desktop & Server Foundation | Tauri+React shell, FastAPI sidecar, PG schema v1, auth, migrations, CI, installer | 1 | Sidecar packaging (D7); TLS on LAN (D18) |
| 3 | Workspaces, Onboarding & Permissions | Workspace isolation, onboarding wizard, roles/permissions, audit | 2 | Isolation correctness (D2); RLS complexity |
| 4 | Clubs, Associations & Competitions | Org model, competitions/grades/seasons, playing conditions | 3 | Historical modelling edge cases |
| 5 | People & Profiles | People registry, roles/history, controlled merge | 4 | Identity merge safety; privacy (D3) |
| 6 | Matches & Scorecard Entry | Scorecard model + fast grid UX, unknown-aware entry | 5 | Grid UX is the hardest piece |
| 7 | Validation, Verification & Data Integrity | Verification state machine, audit rules engine | 6 | Unknown-vs-wrong rule correctness |
| 8 | Cricket Statz & Third-Party Import | Staging pipeline, MXP/CSV parsers, PlayHQ connector | 7 | **Needs real samples + PlayHQ key**; format unknowns |
| 9 | Online Match Discovery | Background discovery jobs, approval queue | 8 | **Legal/ToS** (copyright, access) |
| 10 | Research Centre | Reconstruction, source library, conflicts, verify queue | 7 (parallel w/ 8–9) | Field-level provenance complexity |
| 11 | Media Archive & OneVault | Media storage abstraction, originals, heritage | 6 | OneVault API unknown (D6) |
| 12 | Statistics & Reporting Engine | The one engine + Report Builder + exports | 7 | Correctness; performance |
| 13 | Records, Rankings & Achievements | RMCC catalogue, milestones, captaincy, partnerships | 12 | Counting decisions (D4,D9–D13) |
| 14 | Ask OneStats | NL → deterministic query | 12 | NL approach (D16); no fabrication |
| 15 | Website Publishing & Sync | Publication edge, read-only API, RMCC site | 13 | Lovable site API unknown (D17) |
| 16 | Mobile Records Portal | Responsive read-only portal | 15 | Privacy scoping |
| 17 | Windows, Website & Mobile Release | Harden, package, docs, backups, remote access | 15,16 | Release hardening |
| 18 | RMCC Full-Season Trial | Real-world trial with RMCC | 17 | Real-data surprises; feedback loop |

Optional future: **Cloud Hosting & Wider Commercial Deployment** (architecture already
supports it as a config change).

## Overlap guidance

- Phases 8/9/10 (import, discovery, research) share the staging/approval pipeline and can
  overlap once Phase 7 exists.
- Phase 11 (media) can begin after Phase 6.
- Phases 13 and 14 both build on Phase 12 and can overlap.
- Phases 15/16 share the publishing edge.

## Critical external dependencies (gate certain phases)

- **Phase 8:** real Cricket Statz sample files + PlayHQ API access for RMCC.
- **Phase 9:** legal review of discovery sources.
- **Phase 15:** confirmation of the RMCC Lovable site's integration capability.

## Revised plan — manual acceptance deferred to after Phase 17 (2026-10-26)

By user decision, the combined **manual** acceptance testing is **deferred until after Phase 17** (a
scheduling decision — **no completed phase is accepted** until the user formally approves it). Development
continues through the approved sequence:

- **Phase 14 — Ask OneStats** (NL → deterministic query over the Report Catalogue; no LLM / no external
  service in the first implementation per D16; numbers always from the one engine).
- **Phase 15 — Website Publishing & Sync**, including the **mandatory individual report publishing** with
  permanent public URLs + saved filters, JSON feeds, embeds, branding and publish/unpublish/revoke
  (§29.6), working in the RMCC site's External URL field.
- **Phase 16 — Mobile Records Portal** (responsive read-only portal over the publication edge).
- **Phase 17 — Windows, Website & Mobile Release**, including the **mandatory production installer & USB
  distribution** (three install paths, dependency-managed, upgrade-safe, repair/uninstall, signed where
  feasible — §31.6).

**Post-Phase-17 capabilities (continuing the authorised sequence):**

- **Super Admin User Management & First-Login Security** (see [68](68-user-management-report.md)).
- **Workspace API & Integrations Management** (see [70-api-integrations.md](70-api-integrations.md)):
  clubs/associations configure their own external-provider API credentials from **Settings → API &
  Integrations** — encrypted at rest with a key kept outside the DB, workspace-isolated (FORCE RLS),
  role-gated (`import.configure`), SSRF-protected, test-before-trust, rotatable/revocable, and fully
  audited. No config-file or source edits. This is the reusable secure credential foundation for the
  import/AutoSync connectors (PlayHQ and future providers).

**Acceptance register:** all deferred Phase 11–13 manual tests (including the Report Catalogue tests
RC1–RC15 and the integrity/spot-checks) are preserved and maintained in the **deferred acceptance register**
([62-deferred-acceptance-register.md](62-deferred-acceptance-register.md)); Phase 14–17 acceptance tests are
added there as each phase completes. After Phase 17, the outstanding manual tests are consolidated into one
organised acceptance programme (end-to-end workflows, statistics/report accuracy, profiles/records/awards,
research/provenance, media/OneVault, Ask OneStats, website publishing & public URLs, mobile portal, Windows
install/upgrade/uninstall, backup/restore/DR, permissions/security/isolation, accessibility/UX, performance/
stability), de-duplicated but with complete requirement coverage.

**Per-phase reporting:** at each phase completion — what was implemented, automated test results,
outstanding risks/limitations, updated docs, updated deferred acceptance register, and readiness to
proceed. Development proceeds to the next approved phase unless a **consequential** decision (architecture,
security, privacy, destructive-data, paid service) needs the user. Serious bugs, security, data-corruption
or statistical-integrity issues are fixed immediately, never deferred. The application is **not** declared
production-ready before successful acceptance testing.
