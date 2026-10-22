# OneStats — Phase 1 Planning & Architecture

**Cricket Statistics Made Simple** · Part of the **One** software family
**Status:** Phase 1 (Planning & Architecture) — *awaiting user approval before Phase 2*
**Version:** 1.0 · **Date:** 2026-10-21

> **Phase 1 is documentation and design only.** No application code, database
> schema, migrations or Phase 2 work has been produced. Nothing in these documents
> should be read as "implemented" — a feature appearing here is *planned*, not built.

This folder contains all **38 Phase 1 deliverables** defined in
[`../PHASE1_MASTER_PROMPT.md`](../PHASE1_MASTER_PROMPT.md) §32, one Markdown file per
deliverable, numbered to match. Read [`00-executive-summary.md`](00-executive-summary.md)
first (it is also deliverable 1), then the architecture and database documents.

## Deliverable index

| # | Deliverable | Document |
|--:|---|---|
| 1 | Executive project overview | [00-executive-summary.md](00-executive-summary.md) |
| 2 | Technical architecture | [02-technical-architecture.md](02-technical-architecture.md) |
| 3 | Technology stack assessment | [03-technology-stack-assessment.md](03-technology-stack-assessment.md) |
| 4 | Repository structure | [04-repository-structure.md](04-repository-structure.md) |
| 5 | Database entity relationship design | [05-database-erd.md](05-database-erd.md) |
| 6 | Workspace isolation architecture | [06-workspace-isolation.md](06-workspace-isolation.md) |
| 7 | Permissions matrix | [07-permissions-matrix.md](07-permissions-matrix.md) |
| 8 | Workspace onboarding specification | [08-workspace-onboarding.md](08-workspace-onboarding.md) |
| 9 | Branding and theme specification | [09-branding-and-theme.md](09-branding-and-theme.md) |
| 10 | Application navigation and screen map | [10-navigation-and-screen-map.md](10-navigation-and-screen-map.md) |
| 11 | Cricket organisation data model | [11-organisation-data-model.md](11-organisation-data-model.md) |
| 12 | People and identity model | [12-people-and-identity-model.md](12-people-and-identity-model.md) |
| 13 | Scorecard data model | [13-scorecard-data-model.md](13-scorecard-data-model.md) |
| 14 | Match verification workflow | [14-match-verification-workflow.md](14-match-verification-workflow.md) |
| 15 | Data integrity audit rules | [15-data-integrity-audit-rules.md](15-data-integrity-audit-rules.md) |
| 16 | Cricket Statz import architecture | [16-cricket-statz-import.md](16-cricket-statz-import.md) |
| 17 | Third-party provider feasibility matrix | [17-provider-feasibility-matrix.md](17-provider-feasibility-matrix.md) |
| 18 | Online match discovery architecture | [18-online-match-discovery.md](18-online-match-discovery.md) |
| 19 | Research Centre architecture | [19-research-centre.md](19-research-centre.md) |
| 20 | Media archive architecture | [20-media-archive.md](20-media-archive.md) |
| 21 | OneVault integration contract | [21-onevault-integration-contract.md](21-onevault-integration-contract.md) |
| 22 | Statistics calculation architecture | [22-statistics-engine.md](22-statistics-engine.md) |
| 23 | Complete RMCC report catalogue | [23-rmcc-report-catalogue.md](23-rmcc-report-catalogue.md) |
| 24 | Captaincy calculation specification | [24-captaincy-calculation.md](24-captaincy-calculation.md) |
| 25 | Partnership calculation specification | [25-partnership-calculation.md](25-partnership-calculation.md) |
| 26 | Milestones and achievements specification | [26-milestones-and-achievements.md](26-milestones-and-achievements.md) |
| 27 | Report Builder specification | [27-report-builder.md](27-report-builder.md) |
| 28 | Ask OneStats architecture | [28-ask-onestats.md](28-ask-onestats.md) |
| 29 | Website publishing architecture | [29-website-publishing.md](29-website-publishing.md) |
| 30 | Mobile portal architecture | [30-mobile-portal.md](30-mobile-portal.md) |
| 31 | Windows deployment plan | [31-windows-deployment.md](31-windows-deployment.md) |
| 32 | Backup and disaster recovery plan | [32-backup-and-recovery.md](32-backup-and-recovery.md) |
| 33 | Security and privacy requirements | [33-security-and-privacy.md](33-security-and-privacy.md) |
| 34 | Automated testing strategy | [34-testing-strategy.md](34-testing-strategy.md) |
| 35 | Detailed Phase 2 implementation plan | [35-phase-2-implementation-plan.md](35-phase-2-implementation-plan.md) |
| 36 | Required software and development assets | [36-required-assets.md](36-required-assets.md) |
| 37 | Risk register and outstanding decisions | [37-risk-register-and-decisions.md](37-risk-register-and-decisions.md) |
| 38 | Phase 1 acceptance checklist | [38-acceptance-checklist.md](38-acceptance-checklist.md) |

Supporting documents:
- [18-phase-roadmap.md](18-phase-roadmap.md) — the §31 roadmap (referenced by
  deliverables 1 and 35).
- [16a-cricket-statz-json-analysis.md](16a-cricket-statz-json-analysis.md) — evidence
  record from inspecting the **real** RMCC Cricket Statz JSON export and cross-referencing
  the Cricket Statz UI screenshots (backs deliverables 16, 05, 12, 13, 14, 15, 22, 24, 34).
- [12a-player-profile-and-badges.md](12a-player-profile-and-badges.md) — player-profile
  design and milestone badge catalogue, from inspecting the **real** RMCC player-profile
  page (backs deliverables 12, 26, 29, 30; branding per deliverable 9).
- [20a-mobile-upload-architecture.md](20a-mobile-upload-architecture.md) — mobile image &
  document upload (QR pairing, time-limited sessions, review queue, security); core media
  → Phase 11, mobile UI → Phase 16 (backs deliverables 20, 21, 30, 33).

Phase 2 build: [DEVELOPMENT.md](DEVELOPMENT.md) · [PHASE2_COMPLETION_REPORT.md](PHASE2_COMPLETION_REPORT.md).

## How to read these documents

- **Decisions needing your approval** are collected in
  [37-risk-register-and-decisions.md](37-risk-register-and-decisions.md) and tagged
  `[DECISION]` inline wherever they arise.
- **Unverified external facts** (provider APIs, formats) are tagged `[CANDIDATE]` or
  `[UNVERIFIED]` — they must be confirmed against real samples/agreements in Phase 2.
- Core data-integrity principles are stated once in
  [22-statistics-engine.md](22-statistics-engine.md) and referenced elsewhere:
  **unknown ≠ zero**, **never invent statistics**, **preserve provenance**,
  **no double counting**, **verified data is authoritative**.
