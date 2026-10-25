# Phase 10 — Historical Research Centre: Implementation Report

**Status:** implementation + automated tests complete (2026-10-25) — **awaiting user acceptance.**
Manual acceptance checklist: [55](55-phase10-acceptance.md). Engineering plan: [54](54-phase10-research-centre-plan.md).

Phase 10 transforms OneStats into a historical research platform: discover, collect, examine,
reconstruct, compare, verify and preserve historical cricket information, for volunteers and experienced
researchers alike — while keeping **one canonical match record**, full field-level provenance, and the
approved-only official-statistics rule.

## 1. Implemented functionality

- **Research Centre foundation** (`/manage/research`): a DB-backed dashboard (projects, sources, matches
  under investigation, incomplete scorecards, awaiting verification, conflicts, open tasks, verified).
- **Source Library**: rich source documents (15 types) with full citation + copyright metadata;
  **publication date stored separately from match date**, with precision/uncertainty; file upload with
  integrity hash; duplicate-by-content detection; multiple editions per publication.
- **OCR & text extraction**: local-first pipeline; machine OCR, researcher-corrected transcription and
  structured data kept as **distinct layers**; manual-transcription fallback; scorecard-line hinting.
- **Scorecard reconstruction**: start a provisional draft match holding only what is known (reuses the
  Phase 6 model + Phase 7 approval — no second engine); many sources contribute to one canonical match.
- **Field-level provenance**: every fact traced to its source(s); conflicts detected with both claims
  retained; accept supersedes competitors (kept, never deleted); rejected claims retained with reasons.
- **Verification** reconciled with Phase 7: additive `verified_partial` (present data eligible) and
  `disputed` (held out of statistics); submit-for-review + verify decisions.
- **Historical Research Timeline**: season coverage with a transparent, documented methodology
  (computed classes capped at *partial*; *comprehensive*/*inactive* only via evidence-backed
  assessment; no-matches = *unassessed*).
- **Research Gaps**: real derived categories with samples, one-click conversion to tasks.
- **Research Projects, Tasks, Notes** (evidence classes), and **evidence-grounded assistance**
  (suggestions only, never invented facts; not the Phase 14 assistant).
- **Historical aliases**: former names/abbreviations/spellings/transcription errors broaden search
  without rewriting source text.
- **UI**: a seven-tab Research Centre with a document viewer, plain-language labels and progressive
  disclosure.

## 2. Automated test results

- Backend **486 passing, 2 skipped**; Desktop **58 passing**; `tsc` clean; **ruff** clean.
- Regression green: Phase 7 approval/recalc/statistics (31), Phase 8 import, Phase 9 AutoSync.
- New Phase 10 suites: foundation + RLS isolation, storage, provenance/conflict, OCR (injected engine +
  fallback), reconstruction/multi-source, verification, timeline/gaps, tasks/notes/assistance,
  aliases/connectors, worldwide/copyright/pagination/OneVault.

## 3. Supported document types

newspaper article · clipping · edition · scorebook (scanned) · handwritten scorecard · printed scorecard
· photograph · PDF · image · club record · association annual report · cricket publication · archived
website · online database · manual reference. Uploads accept PNG/JPEG/WebP/TIFF/GIF images and PDF (30 MB
default cap), stored unaltered with a SHA-256 hash.

## 4. Verified OCR capabilities

- A **local** OCR engine (Tesseract via `pytesseract`) is used **when installed**; the pipeline detects
  it lazily and degrades to **manual transcription** when absent. OCR confidence is recorded and OCR
  output is never treated as verified truth.
- **Not** verified / not claimed: handwriting recognition and specific multilingual OCR accuracy (source
  `language` is captured; recognition quality is not asserted without measured evidence). Multi-column
  newspaper layout parsing is best-effort text extraction plus a scorecard-line hint, not guaranteed
  structured parsing. No paid cloud OCR is used — that would require explicit approval.

## 5. Verified archive integrations

**None.** PlayHQ, Play-Cricket, CricketArchive, Trove and the generic newspaper/library connectors are
registered **interface-only** (documented, non-fetching). No provider is operational until verified,
legitimate access and a real-data sample exist. See outstanding dependencies below.

## 6. Outstanding external dependencies

| Provider | Needs |
|---|---|
| PlayHQ | Valid approved 36-char UUID API key (Phase 9 Test 16, still blocked) |
| Play-Cricket (ECB) | ECB API key + site registration + sample |
| CricketArchive | Commercial licence + sample |
| Trove (NLA) | Trove API key + adherence to NLA terms + sample |
| Newspaper / library collections | Licensed/permitted access + sample per provider |

Each is recorded in [52](52-phase9-external-dependencies.md). **Phase 10 does not depend on any of
them** — research runs on uploads, manual entry and fixtures.

## 7. Known limitations

- No verified live archive connector ships in this phase (above).
- OCR quality depends on a locally installed engine; handwriting/multilingual accuracy not asserted.
- Structured scorecard parsing from OCR is assisted (hints), not fully automatic.
- Statistical inclusion of a `verified_partial` match covers the data actually present; field-scoped
  partial statistical eligibility beyond that is a future refinement.
- The in-process desktop job runner covers the Windows desktop (shared with Phase 9).

## 8. Manual acceptance instructions

See [55](55-phase10-acceptance.md): 24 guided tests in the Sandbox (open centre, create project, upload,
metadata, OCR + correction, partial match, multi-source build, conflict detect/resolve, verify partial,
statistics isolation, timeline, gaps, alias search, resume, isolation/permissions, provenance/audit,
Phase 9 integration, historical dates, recovery, and a real-world Rhymney/Moyston reconstruction).

## 9. Readiness for Phase 11 (OneVault)

Source files use a **storage abstraction** with a stable reference, SHA-256 integrity hash, size and
content type on each record, and source↔match relationships preserved — ready to link or transfer to
OneVault without re-coupling. The full media-archive system is intentionally **not** built here.
**Do not begin Phase 11 without explicit user authorisation.**

## 10. Core principles upheld

One match = one canonical record; evidence before assumptions (unknown ≠ zero, never invented); original
evidence preserved and traceable; conflicting evidence kept visible; progressive save/resume
reconstruction; historical accuracy over completeness; copyright/access respected; no paywall/anti-bot
bypass; no capability claimed without tested evidence.
