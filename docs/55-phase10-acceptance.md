# Phase 10 — Historical Research Centre: Manual Acceptance Checklist

For a reviewer in the **OneStats Sandbox** workspace. The Research Centre is reached from **Club
Management → Research Centre** (`/manage/research`). Start the backend + desktop app (see
[46](46-phase7-acceptance.md)). Sign in as a user with `research.manage` (and `research.verify` for the
verification steps) — the Super Admin and Workspace Admin have both.

Record each test **Pass / Fail / Blocked**. Investigate and fix failures before continuing. Simulated
capabilities are never recorded as verified live integrations.

## Scope of live sources (read first)

No verified live third-party archive connector ships in this phase. PlayHQ (Phase 9 Test 16),
Play-Cricket, CricketArchive **and** the historical-newspaper providers (Trove, generic newspaper/
library collections) are registered **interface-only** — documented, not operational — pending verified,
legitimate access ([52](52-phase9-external-dependencies.md), [54 §4](54-phase10-research-centre-plan.md)).
All Phase 10 research runs on **uploaded documents, manually entered references and fixtures** and does
**not** depend on any external credential. OCR uses a **local** engine when installed, otherwise falls
back to manual transcription (no paid cloud OCR without your approval).

## Checklist

1. **Open the Research Centre.** Club Management → Research Centre. The Dashboard shows real counts
   (zeros on a fresh workspace), not fabricated numbers.
2. **Create a research project.** Research Projects → enter a title (e.g. "Rhymney CC 1891–1900") →
   Create project. It appears in the list.
3. **Upload a historical newspaper image or PDF.** Source Library → Add source (title, type,
   publication, publication date) → then **Upload document** on that row. The OCR-status badge moves to
   *pending*.
4. **Enter and verify source metadata.** Confirm publication date is stored **separately** from any
   match date, and copyright/usage fields are retained.
5. **Extract text using OCR.** On a source with a document, click **Run OCR**. If a local OCR engine is
   installed the machine text is stored; if not, the source is marked for **manual transcription**
   (expected, not a failure) — record which occurred.
6. **Correct inaccurate OCR text.** Provide a corrected transcription; confirm the machine OCR text is
   kept **alongside** the correction (not overwritten). *(API: `/extractions/{id}/correct`.)*
7. **Create a partial historical match.** Review & Verify → **Start a reconstruction**. A draft match is
   created holding only what is known (date may be unknown) — nothing invented.
8. **Add batting information from a newspaper.** Record a batting claim against the match with its source
   (provenance). Unknown figures stay unknown, never 0.
9. **Add bowling information from a second source.** Record a bowling claim from a different source;
   both sources now contribute to the **one** match.
10. **Link multiple newspaper editions to one match.** Attach several sources (editions) to the same
    match; confirm no duplicate match is created.
11. **Detect conflicting source values.** Record two different values for the same field from two
    sources; confirm a conflict is detected and **both** claims are retained.
12. **Resolve a conflict while preserving both original claims.** Accept one claim; confirm the other is
    **superseded (kept, not deleted)** and the decision/reason is recorded.
13. **Verify a partially reconstructed scorecard.** Review & Verify → **Verify partial**. The match
    becomes `verified_partial`; its present data is statistics-eligible, without pretending the
    scorecard is complete.
14. **Confirm unapproved research does not affect official statistics.** A draft/disputed reconstruction
    contributes nothing to official statistics (only verified states do).
15. **Open the Historical Research Timeline.** Timeline tab shows seasons with a coverage class and the
    transparent methodology note; a season with no known matches is **Unassessed**, never a fabricated %.
16. **Identify and investigate a research gap.** Research Gaps lists real categories (missing scorecards,
    unknown results/dates, …); **Create task** turns a gap into a work item.
17. **Search historical matches using an old club name or alias.** Register an alias (Source Library data
    / `/aliases`) and confirm `/aliases/expand` returns the variants — the original source text is never
    rewritten.
18. **Resume an unfinished research project.** Reopen the project/tasks later; saved work and partial
    reconstructions persist.
19. **Confirm workspace isolation and permissions.** Research data is confined to the Sandbox workspace;
    verification actions require `research.verify`.
20. **Verify source provenance and research audit history.** From a match, trace each field to its
    supporting source(s); confirm decisions are audited.
21. **Confirm integration with Phase 9 discoveries.** AutoSync discoveries still import as draft and flow
    into the research review queue; the research matches list surfaces them.
22. **Verify historical dates and unknown-field handling.** Enter a pre-1900 match with year/season/range
    precision; confirm precision + uncertainty are retained and unknown ≠ zero throughout.
23. **Confirm recovery after interrupted processing.** The Phase 9 background job engine reconciles
    interrupted jobs on restart (shared infrastructure); long OCR/import work resumes.
24. **Perform a practical real-world historical reconstruction** using genuine Rhymney/Moyston source
    material: add the source(s), extract/transcribe, record provenance, resolve any conflict, and submit
    for verification — end to end.

## Automated coverage (last run)

| Suite | Result |
|---|---|
| Backend (pytest) | **486 passing, 2 skipped** (DB tests roll back) |
| Desktop (vitest) | **58 passing**; `tsc` clean; `vite build` path unaffected |
| Ruff | clean |
| Regression | Phase 7 approval/recalc/stat (31), Phase 8 import, Phase 9 AutoSync — all green |

New Phase 10 backend tests: research foundation + RLS isolation, Source Library + storage
(round-trip/traversal/limits/duplicate-by-hash/editions), field provenance + conflict resolution, OCR
pipeline (injected engine + manual fallback + correction), reconstruction + multiple-sources-one-match,
verification (verified_partial eligible / disputed excluded / approved flow unchanged), timeline +
gaps, tasks/notes/assistance, archive connectors interface-only + alias expansion, worldwide/copyright/
pagination/OneVault.

**Phase 10 implementation + automated tests complete — awaiting user acceptance. Do not begin Phase 11
without explicit authorisation.**
