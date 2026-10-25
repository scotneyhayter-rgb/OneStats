# Phase 10 — Historical Research Centre: Implementation Outline

**Status:** in development (authorised 2026-10-25). This is the engineering plan that the autonomous
Phase 10 build follows. It records the architecture, what is **reused** vs **new**, the identified
(non-blocking) decisions, external dependencies, and the stage sequence. Design refs: research centre
[19](19-research-centre.md); scorecard model [13](13-scorecard-data-model.md); verification
[14](14-match-verification-workflow.md); online discovery [18](18-online-match-discovery.md); integrity
[15](15-data-integrity-audit-rules.md); navigation [10](10-navigation-and-screen-map.md).

## 0. Phase 9 acceptance gate (verified)

Confirmed before starting (Phase 10 §2): Phase 9 is **conditionally accepted**
([53](53-phase9-handover.md)); Tests 1–15 **passed**; Test 16 (live PlayHQ) **blocked, not passed**;
no other Phase 9 defects (440 backend / 56 desktop pass; ruff/tsc clean). **Phase 10 does not depend on
PlayHQ credentials** — all research development runs on uploaded/entered sources and fixtures.

## 1. Architecture — reuse, never duplicate

| Concern | Reused (existing) | New in Phase 10 |
|---|---|---|
| Scorecard data (batting/bowling/FOW/innings/officials) | Phase 6 `match`/`innings`/`batting`/`bowling`/`fow` + entry system (deliverable 13) | — (reconstruction writes to the **same** tables; no second engine) |
| Approval / verification | Phase 7 `match.approval_status` (`draft`→`awaiting_approval`→`approved`/`rejected`); approved-only statistics | Research verification maps onto this; adds `verified_partial` + `disputed` as **additive** states (Stage 10.11) |
| Source-per-match provenance | Phase 8 `match_source` (source_system/ref, edition, sha256, recorded_fields) | **Field-level** provenance `field_provenance` (Stage 10.9) |
| Multiple sources → one match | Phase 8 `match_source` + attach/compare (R1) | Research-facing compare/conflict UI (Stages 10.8/10.10) |
| Discovery / coverage | Phase 9 `discovery_item`/`discovery_coverage`/`sync_source` | Research-project-scoped discovery launch (Stage 10.3); season coverage assessment (Stage 10.12) |
| CCDM normalisation / dedupe | Phase 8 `importing/` (CanonicalDataset, dedupe, pipeline) | OCR→CCDM extraction adapters (Stage 10.6) |
| Workspace isolation / permissions | FORCE RLS + GUC; role/permission tables | perms `research.manage`, `research.verify` |
| Audit | `audit` domain | research decision/audit trails reuse it |

**One canonical match record** is enforced exactly as Phase 8/9 do it: dedupe + `match_source`
attach, never a second match row per source/edition.

## 2. New schema (additive, FORCE RLS, workspace-scoped)

Spine created in **0038** (Stage 10.1): `research_project`, `research_source` (rich Source-Library
document metadata incl. **publication_date separate from match date**, precision/uncertainty,
copyright/usage, file_ref + sha256 + ocr_status), `research_source_match` (link, many-to-many → one
canonical match), `research_note` (evidence class: verified/supported/oral_history/unverified/disputed),
`research_task` (gap → work queue). Later migrations: `field_provenance` (10.9),
`source_extraction` (OCR original + corrected + method/version/confidence, 10.6),
`season_coverage` assessment (10.12). Scalable schema (JSONB scope/value, keyed rows) — **not** a
proliferation of per-field tables.

## 3. Identified decisions (non-blocking — proceeding under autonomy)

- **Approval states:** extend `match.approval_status` CHECK additively with `verified_partial` and
  `disputed` (Stage 10.11) so research verification reconciles with the Phase 7 machine rather than
  creating a parallel one. Statistics eligibility stays **approved-only**; `verified_partial` feeds only
  its verified scope; `disputed` never feeds official stats.
- **OCR engine (Stage 10.6):** assess a **local** engine (Tesseract via `pytesseract`, a system binary)
  before any paid cloud OCR. OCR output is never treated as verified truth — stored distinctly from the
  corrected transcription and the structured data. **No paid AI/OCR provider is used without explicit
  user approval.** If no local engine is present, manual transcription is the fallback; the standard
  test suite never depends on an OCR binary (extraction is tested with injected fixtures).
- **Source storage (Stage 10.20):** a storage **abstraction** (`media_root`-based now, like Phase 9
  logos) with original reference + integrity hash, so files can later move/link to OneVault (Phase 11)
  without re-coupling. No Phase 11 media system built now.
- **Navigation:** Research Centre is surfaced as a workspace management section (`/manage/research`),
  consistent with the implemented pattern (AutoSync/Import live under `/manage/*`), realising the
  design's "Matches → Research Centre" five areas as in-screen tabs (deliverable 10 §10.3: max two nav
  levels; deep tasks use tabs).

## 4. External dependencies (do not block the phase)

- **Historical newspaper archives (Trove et al., Stage 10.3):** investigate legitimate access; register
  as **interface-only** until verified access terms exist, exactly as Phase 9 does for live connectors.
  No access is assumed from a website alone; no paywall/anti-bot bypass. Development uses fixtures +
  uploaded documents.
- **PlayHQ live connector:** still blocked (Phase 9 Test 16) — unrelated to Phase 10 progress.

## 5. Stage sequence (each: implement → tests → regression → commit)

10.1 Foundation (nav + routes + DB-backed dashboard + spine schema) · 10.2 Source Library · 10.3
Archive discovery integration (interface-only + fixtures) · 10.4 Historical name/alias recognition ·
10.5 Document viewer / research workspace · 10.6 OCR & text extraction (local-first) · 10.7 Scorecard
reconstruction (reuse Phase 6/7) · 10.8 Multiple sources → one match · 10.9 Field-level provenance ·
10.10 Conflict detection/resolution · 10.11 Verification workflow (reconcile Phase 7) · 10.12 Research
timeline (season coverage) · 10.13 Research gaps/coverage analysis · 10.14 Projects & work queues ·
10.15 Notes & evidence quality · 10.16 Research assistance (evidence-grounded suggestions; no Ask
OneStats) · 10.17 Worldwide historical cricket · 10.18 Copyright/access responsibilities · 10.19
Performance/large datasets · 10.20 OneVault readiness · 10.21 UX · 10.22 Automated tests · 10.23 Manual
acceptance checklist + final report.

## 6. Core principles enforced throughout (Phase 10 §3)

One match = one canonical record; evidence before assumptions (unknown ≠ zero, never invented);
original evidence preserved + traceable; conflicting evidence kept visible (both claims retained);
progressive reconstruction (save/resume partial work); historical accuracy over completeness.
