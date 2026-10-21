# 38. Phase 1 Acceptance Checklist

**Deliverable 38 of 38** · §32, §34

Use this to accept Phase 1 and authorise Phase 2. Each item maps to a deliverable.

## 38.1 Deliverables produced (all 38)

- [x] 1 Executive project overview — [00-executive-summary.md](00-executive-summary.md)
- [x] 2 Technical architecture — [02-technical-architecture.md](02-technical-architecture.md)
- [x] 3 Technology stack assessment — [03-technology-stack-assessment.md](03-technology-stack-assessment.md)
- [x] 4 Repository structure — [04-repository-structure.md](04-repository-structure.md)
- [x] 5 Database ERD — [05-database-erd.md](05-database-erd.md)
- [x] 6 Workspace isolation — [06-workspace-isolation.md](06-workspace-isolation.md)
- [x] 7 Permissions matrix — [07-permissions-matrix.md](07-permissions-matrix.md)
- [x] 8 Workspace onboarding — [08-workspace-onboarding.md](08-workspace-onboarding.md)
- [x] 9 Branding & theme — [09-branding-and-theme.md](09-branding-and-theme.md)
- [x] 10 Navigation & screen map — [10-navigation-and-screen-map.md](10-navigation-and-screen-map.md)
- [x] 11 Organisation data model — [11-organisation-data-model.md](11-organisation-data-model.md)
- [x] 12 People & identity model — [12-people-and-identity-model.md](12-people-and-identity-model.md)
- [x] 13 Scorecard data model — [13-scorecard-data-model.md](13-scorecard-data-model.md)
- [x] 14 Match verification workflow — [14-match-verification-workflow.md](14-match-verification-workflow.md)
- [x] 15 Data integrity audit rules — [15-data-integrity-audit-rules.md](15-data-integrity-audit-rules.md)
- [x] 16 Cricket Statz import — [16-cricket-statz-import.md](16-cricket-statz-import.md)
- [x] 17 Provider feasibility matrix — [17-provider-feasibility-matrix.md](17-provider-feasibility-matrix.md)
- [x] 18 Online match discovery — [18-online-match-discovery.md](18-online-match-discovery.md)
- [x] 19 Research Centre — [19-research-centre.md](19-research-centre.md)
- [x] 20 Media archive — [20-media-archive.md](20-media-archive.md)
- [x] 21 OneVault integration contract — [21-onevault-integration-contract.md](21-onevault-integration-contract.md)
- [x] 22 Statistics engine — [22-statistics-engine.md](22-statistics-engine.md)
- [x] 23 RMCC report catalogue — [23-rmcc-report-catalogue.md](23-rmcc-report-catalogue.md)
- [x] 24 Captaincy calculation — [24-captaincy-calculation.md](24-captaincy-calculation.md)
- [x] 25 Partnership calculation — [25-partnership-calculation.md](25-partnership-calculation.md)
- [x] 26 Milestones & achievements — [26-milestones-and-achievements.md](26-milestones-and-achievements.md)
- [x] 27 Report Builder — [27-report-builder.md](27-report-builder.md)
- [x] 28 Ask OneStats — [28-ask-onestats.md](28-ask-onestats.md)
- [x] 29 Website publishing — [29-website-publishing.md](29-website-publishing.md)
- [x] 30 Mobile portal — [30-mobile-portal.md](30-mobile-portal.md)
- [x] 31 Windows deployment — [31-windows-deployment.md](31-windows-deployment.md)
- [x] 32 Backup & recovery — [32-backup-and-recovery.md](32-backup-and-recovery.md)
- [x] 33 Security & privacy — [33-security-and-privacy.md](33-security-and-privacy.md)
- [x] 34 Testing strategy — [34-testing-strategy.md](34-testing-strategy.md)
- [x] 35 Phase 2 implementation plan — [35-phase-2-implementation-plan.md](35-phase-2-implementation-plan.md)
- [x] 36 Required assets — [36-required-assets.md](36-required-assets.md)
- [x] 37 Risk register & decisions — [37-risk-register-and-decisions.md](37-risk-register-and-decisions.md)
- [x] 38 Acceptance checklist — this document

Plus supporting: [18-phase-roadmap.md](18-phase-roadmap.md) (§31) and
[16a-cricket-statz-json-analysis.md](16a-cricket-statz-json-analysis.md) (real Cricket
Statz JSON + UI-screenshot evidence backing deliverables 16, 05, 12, 13, 14, 15, 22, 24, 34).

## 38.2 Hard-constraint compliance (§33 development rules)

- [x] **Planning only** — no app code, schema, migrations or Phase 2 work produced.
- [x] **Unknown ≠ zero** — modelled throughout (nullable + known-minimum, deliverables 5,13,22).
- [x] **Never invent statistics** — engine returns unknown/insufficient (deliverable 22,28).
- [x] **Preserve provenance** — sources, field-level provenance, evidence (deliverables 5,19).
- [x] **No double counting** — normalised model + derived stats (deliverables 5,13,22,25).
- [x] **Protect verified data** — verification state machine + audit (deliverable 14).
- [x] **Enforce permissions** — matrix + service-layer enforcement (deliverable 7).
- [x] **Workspace isolation** — 3-layer + RLS (deliverable 6).
- [x] **Least-privilege DB** — app uses `onestats_app`, never superuser; no plaintext secrets (deliverables 31,33).
- [x] **Respect external source restrictions** — no bypass/scrape; copyright respected (deliverables 17,18,33).
- [x] **OneVault optional** — works fully without it (deliverable 21); OneVault not modified.
- [x] **Protect junior/private data** — hidden by default; never age-rank on uncertain DOB (deliverables 24,33).
- [x] **Test all calculations** — golden fixtures as release gate (deliverable 34).
- [x] **OneVault / other projects untouched** — only `C:\OneProjects\OneStats\docs\` written.
- [x] **Real Cricket Statz export validated read-only** — original file inspected but **not**
      modified and **not** copied into the repo; real RMCC data kept out of source control and
      test fixtures (deliverables 16, 16a, §33).
- [x] **Identity: unique IDs, not names** — same-named distinct players (two "Bonner A")
      kept separate; no auto-merge; stats key on `person_id` (deliverables 12, 15).
- [x] **Player Identity Management (Find & Merge Duplicates)** designed into the schema —
      `person_source_identity`, reversible `person_merge`, `person_distinct_assertion`;
      suggest-not-auto-merge; recalc-from-records; same-match conflict blocking; undo/split;
      reuse-on-reimport. Confirmed examples modelled: "Bonner A" (keep separate), "Walker D"
      (mergeable). Tests A–F specified (deliverables 12 §12.3a, 34).
- [x] **Player profile design + milestone badge catalogue** from the **real** RMCC profile
      page — workspace-branded (not hardcoded RMCC), engine-derived stats, merged-identity
      aware, historical/no-photo players supported, responsive, publishable
      ([12a-player-profile-and-badges.md](12a-player-profile-and-badges.md)).
- [x] **Historical web scraping** (core, Phases 9–10) — publicly-accessible sources only,
      per-source adapters + OCR with preserved uncertainty, confidence + provenance, human
      review, no name-only merges, strict compliance guardrails (`[DECISION D20]`,
      deliverable 18 §18.2a).
- [x] **Historical Research Timeline** — season coverage classes incl. **Unassessed**
      (never a fabricated %), completeness≠verification, confirmed-inactive≠missing,
      recalc-after-findings, audited, with timeline/season-detail/task-queue/evidence panels
      (`[DECISION D21]`, deliverable 19 §19.6).

## 38.3 Sign-off to begin Phase 2

- [ ] Architecture approved (deliverable 2) and key decisions resolved: **D1, D2, D7,
      D18** (🔴) at minimum.
- [ ] Counting/calculation decisions acknowledged (D4, D9–D15) — can be finalised before
      Phase 12/13; forfeit/streak rules (D10, D15) still to confirm. **D12
      (bowling-partnership method) is RESOLVED** (deliverable 25 §25.3).
- [ ] Privacy defaults (D3) and Ask OneStats NL approach (D16) acknowledged.
- [ ] User to provide: `onestats_app` credential setup; (for Phase 8) PlayHQ API access +
      real Cricket Statz samples; (for Phase 15) RMCC website integration details.
- [ ] Explicit approval given to start Phase 2.

> Nothing in Phase 2 begins until this sign-off is given.
