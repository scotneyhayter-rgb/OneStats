# Phase 8 — Manual Acceptance Checklist & Completion Report

Universal third-party import framework. For a reviewer in the **OneStats Sandbox** workspace. No
production or other workspace records are modified. Start the backend + desktop app (see
[46](46-phase7-acceptance.md) for startup), sign in, open the Sandbox.

## Consolidated test results (last run)

| Suite | Result |
|---|---|
| Backend (pytest) | **409 passing, 2 skipped** (DB tests roll back; 2 skips are first-super-admin bootstrap) |
| Desktop (vitest) | **54 passing**; `tsc` clean; `vite build` OK |
| Ruff | clean |
| CricketStatz regression | **28 import tests green** (behaviour unchanged) |

New Phase 8 automated coverage: adapter core/registry, CricketStatz→CCDM, mapping engine + CSV,
Excel/JSON/XML (cross-format equivalence, detection routing, XML entity/XXE rejection),
source-agnostic promotion, end-to-end generic import, duplicate detection + multiple-sources/R1,
universal import API + wizard flow, provenance endpoint, recovery (R2), performance (R3), and the
Phase 9 AutoSync interfaces.

## Checklist

1. **Universal import — CSV.** Import Data → **Other formats** tab. Choose a match-summary CSV
   (columns: Date, HomeTeam, AwayTeam, Competition, Grade, Venue, Result, Format, Round). Confirm the
   format is **detected** as "CSV match summary", **Preview** shows counts and persists nothing, and
   **Import** creates the matches as **drafts**.
2. **Excel / JSON / XML.** Repeat with a `.xlsx`, a JSON array of match objects, and an XML
   `<match>` document. Confirm each is detected and imports the same way.
3. **Format detection + override.** Confirm the detected format can be changed in the dropdown before
   importing; an unrecognised file shows a clear "no adapter recognised" message.
4. **No duplicates on re-import.** Import the same file again; confirm matches are **matched, not
   duplicated** (and people/teams likewise).
5. **Duplicate detection & multiple sources.** For a match that already exists from another source,
   confirm it is offered as a possible/exact duplicate and can be recorded as an **additional
   source** (e.g. a newspaper edition) — the existing scorecard is **not overwritten**.
6. **Provenance (scorecard → source).** Open an imported match → **Sources & Provenance**. Confirm
   the source(s) are listed, and that **conflicting** source values (if any) are flagged for review,
   never auto-resolved.
7. **CricketStatz unchanged.** Confirm the **CricketStatz** tab still imports exactly as before
   (captains/keepers/toss, dismissal codes, FOW, auto-partnerships), with no duplicates on re-import.
8. **Approval integration.** Confirm imported matches are **draft** (not auto-approved) and only feed
   official statistics once approved (Phase 7 workflow).
9. **Workspace isolation.** Confirm every import is confined to the Sandbox workspace.
10. **Malformed input.** Confirm a malformed/garbage file is rejected with a clear message and nothing
    is imported.

## Supported formats

Implemented & tested: **CricketStatz** (JSON export), **CSV**, **Excel (.xlsx)**, **structured JSON**
(array of match objects), **structured XML** (`<match>` elements). A reusable mapping engine maps
columns to the canonical model; column names are remappable.

## Unsupported third-party formats (and what is needed)

- **PlayHQ**, **Play-Cricket**: the framework is **interface-ready** (a new adapter is a detect/parse/
  normalise module against the Canonical model — no pipeline change). Native adapters are **not
  claimed** because their real export structure has not been verified. To add them we need a
  **legitimate sample export** from each (ideally a few matches with scorecards) to confirm field
  names, nesting, dismissal/result encodings and identifiers, plus permission to use the sample as a
  deterministic test fixture.
- **PDF / scanned scorecards / newspaper images (OCR):** deferred to the **Research Centre** phase;
  Phase 8 establishes the import interface only.

## Known limitations / deferred

- **CricketStatz staging convergence** onto the generic stager — a documented technical improvement,
  not a defect ([47](47-phase8-import-framework.md)).
- **Batched-insert staging / streaming parse** for very large (100k+) datasets — documented
  optimization; current throughput (~75–93 matches/s) suits the thousands-of-matches target.
- **Run-out & wicket reconciliation** — Phase 12 ([48](48-phase12-dismissal-reconciliation.md)); the
  needed dismissal data is retained at import.
- **AutoSync discovery engine** — Phase 9; the service interfaces (sources, modes, cursors,
  orchestration reusing import/approval/recalc) are in place.

**Phase 8: implementation + automated tests complete — awaiting user acceptance. Do not begin Phase 9
until Phase 8 is accepted.**
