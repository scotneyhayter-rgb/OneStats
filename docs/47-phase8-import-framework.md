# Phase 8 — Universal Third-Party Import Framework (internal design)

_Authorised 2026-10-25. Target: feature-complete trial build by 31 Oct 2026; extended testing /
historical research through Mar 2027. Quality, data integrity and security are never traded for
speed._

This is the design that STEP 2 of the Phase 8 authorisation requires **before** substantial changes.
It extends the existing architecture; it does not create a competing import system. The CricketStatz
importer is retained and becomes the first adapter without breaking previously successful imports.

---

## 0. Additional approved requirements (2026-10-25)

Integrated into the existing stages — no extra stages:

- **R1 — Multiple historical sources per match.** A match may carry several source records (e.g.
  different newspaper editions). Source-specific evidence and *conflicting* values are preserved for
  administrator review; verified information is never silently overwritten. → model & provenance
  (§3.1, §6), duplicate handling "attach, don't overwrite" (§5), wizard review (§3.3), stages
  **8.5 / 8.7**.
- **R2 — Import recovery.** Interruption/recovery is tested during **database promotion** as well as
  parsing/staging; retries cannot create duplicate or partially-committed scorecards (staging-first +
  single-transaction promotion + idempotent source-ref keys). → stages **8.8 / 8.10**.
- **R3 — Large-dataset reliability.** Memory-efficient processing is verified with realistic datasets
  of thousands of matches; performance results recorded and significant bottlenecks addressed. →
  stages **8.8 / 8.10**.

## 1. Principles (inherited, non-negotiable)

Carried from Phases 5–7 and applied to every adapter:

- **Never fabricate.** Unknown stays unknown (never 0). Missing wickets, scores, players, captains,
  keepers and toss are left unresolved, not invented.
- **Never auto-merge uncertain identities.** Name similarity never merges people or teams; ambiguity
  is surfaced for administrator review.
- **Provenance preserved.** The verbatim source row, source system, source identifiers and original
  names/abbreviations are retained; a scorecard can be traced back to its source.
- **Idempotent & non-destructive.** Re-importing an identical source creates no duplicate matches,
  innings, players or statistics. Migrations stay additive.
- **Approval-gated statistics.** Imported scorecards enter **draft** — never silently approved. Only
  approved scorecards feed the official-statistics ledger (Phase 7.8); re-imports never double-count;
  corrections/merges invalidate dependent calculations.
- **Workspace isolation.** Every table is workspace-scoped under FORCE RLS; imports target one
  workspace chosen explicitly.
- **No raw-JSON/DB literacy required** of ordinary users.

## 2. What already exists and is reused (do not rebuild)

| Capability | Where | Reuse in Phase 8 |
|---|---|---|
| Staging tables `import_batch` (source_system, source_filename, source_sha256, counts, status, provenance) + `import_staging_record` (entity_type, source_ref, raw, normalised, status, resolution, matched_canonical_id, issues) | `0010_import_staging.py` | **Source-agnostic already.** The common staging substrate for all adapters. |
| Generic batch endpoints: list / get / records / **validate** / **promote** / **cancel** / **rollback** | `api/v1/imports.py` | The core pipeline's control surface; adapters feed the same batch lifecycle. |
| CricketStatz parse/stage/promote, HOWOUT legend, result/matchtype maps, captain/keeper/toss, club linking, backfill | `domain/imports.py` | Refactored into `adapters/cricket_statz.py` behind the adapter contract — behaviour unchanged, regression tests stay green. |
| Person identity, duplicate candidates, non-auto-merge, merges | `domain/people.py`, `person_resolution.py` | The matching stage calls these; no new identity engine. |
| Historical team names & aliases | Phase 7.6 | Alias-aware team matching. |
| Approval workflow + recalculation ledger | Phase 7.1 / 7.8 | Imported matches → draft; approval drives recalc; merges invalidate. |
| Import Wizard (analyse → select → preview → import → results; client `buildSlice`) | `features/import/ImportWizard.tsx` | Generalised into the Universal Import Wizard; `buildSlice` becomes adapter-driven. |

## 3. Target architecture

### 3.1 Canonical Cricket Data Model (CCDM)

A single normalised intermediate representation every adapter produces, mirroring the existing
`normalised` payloads so the staging/matching/promotion code is shared. Entities: **Club, Team
(with aliases), Competition, Season, Grade, Venue, Person, Match (teams/home-away, captains,
keepers, toss, result, format, classification, round, date+precision), Innings (+extras), Batting
entry (+dismissal type & source code), Bowling entry, Fall of wicket, Partnership.** Every entity
carries `source_system`, `source_ref` and, where present, `source_display_name`. Unknowns are
explicit nulls; numbers never coerced to 0.

### 3.2 Adapter contract

```
class SourceAdapter(Protocol):
    format_id: str                 # e.g. "cricket_statz", "csv_scorecard", "generic_json"
    display_name: str
    def detect(sample: bytes | str, filename: str) -> float      # 0..1 confidence
    def parse(content) -> RawDataset                              # verbatim rows, no interpretation
    def normalize(raw, mapping=None) -> CanonicalDataset          # -> CCDM, provenance attached
    capabilities: set[str]         # {matches, scorecards, people, toss, ...}
```

Adapters do **only** detection + parsing + normalisation. Everything downstream (staging, matching,
validation, preview, commit, provenance, rollback, error reporting, retries) is the shared **core
pipeline** and is identical for all sources. Adapters register in a registry; new adapters are added
without touching the core.

### 3.3 Core pipeline (source-agnostic)

`detect format → parse → normalize (CCDM) → stage (import_batch + records) → match (person/club/
competition/team/venue/match, alias- & confidence-aware) → validate (Phase 7 aggregation) → preview
(nothing persists) → administrator review → controlled commit/promote → provenance → report`. This
is the existing CricketStatz flow lifted to operate on the CCDM rather than CS-specific fields.

## 4. Supported formats (STEP 4)

1. **CricketStatz** — existing, refactored to an adapter (regression-locked).
2. **CSV** — reusable mapping templates for common scorecard column layouts; user-confirmable mapping.
3. **Excel (.xlsx)** — same mapping engine over sheets; `openpyxl`.
4. **Structured JSON** — generic, with mapping templates.
5. **Structured XML** — generic, with mapping templates.

Native adapters for proprietary services (**PlayHQ**, **Play-Cricket**) are implemented **only** when
their real export structure is verified against legitimate sample data — otherwise documented as
"interface ready, awaiting verified sample" (see §10). PDF/scanned/OCR research belongs to the
Research Centre phase; Phase 8 establishes the import interface only.

## 5. Duplicate detection (STEP 7)

Confidence-based match identification over: existing source identifiers (exact), then date +
competition/season + grade + both teams (alias-aware) + format + venue + innings totals.
**Exact** (same source id, or a full-field match) vs **possible** (partial) are distinguished;
possibles are never silently merged — the administrator chooses. Re-import of an identical source is
an exact match → no new records.

**R1 — attach, don't overwrite.** When a new source describes an existing match, it is recorded as an
*additional* source (a `match_source` row: source system/ref, checksum, the source's own field
values). Values differing from already-stored/verified ones are retained as **conflicts for
administrator review**, never silently applied — a second newspaper edition adds evidence, it does
not mutate the approved scorecard. Adding verified information is additive and leaves other trusted
records intact.

## 6. Provenance & import history (STEP 8)

Reuse `import_batch`/`import_staging_record`; populate `source_sha256` (checksum) for every import;
add an accessible **Import History** view (batches, counts, warnings, outcome, who/when/workspace)
and scorecard→source tracing. Retain the source payload or a reliable reference per storage/security
policy. **R1:** a canonical match links to one-or-more `match_source` records (multiple editions),
each with its own provenance and field values, so conflicting accounts are both traceable.

## 7. Approval & recalculation integration (STEP 9)

Unchanged authority: imported matches → **draft**; import never approves. Approved stats are never
overwritten by unapproved re-imports; approving a revision triggers recalculation; repeated imports
never double-count; corrections/identity merges invalidate dependent contributions (ledger already
merge-aware). Historical bulk approval stays permissioned and audited.

## 8. Resumability, batching & error handling (STEP 10)

Batch processing with progress reporting, recoverable failures, safe retries, cancellation,
restart-after-interruption, useful errors and partial-success reporting. Staging first means a failed
commit never leaves partially-committed scorecards; the batch is the unit of recovery. **R2:**
interruption/recovery is tested during **promotion** (commit) as well as parsing/staging — a
single-transaction promotion rolls back wholly on failure, and idempotent source-ref keys mean a
retry re-commits exactly once (no duplicate or half-written scorecards). **R3:** memory-efficient
processing is verified against realistic datasets of **thousands of matches**, with performance
results recorded and significant bottlenecks addressed (stream/chunk parsing; batched promotion;
indexed source-ref lookups). Designed for
thousands of matches without loading everything into memory (stream/parse in chunks; the wizard
already slices selected matches).

## 9. Phase 9 AutoSync readiness (STEP 11)

Expose the pipeline as reusable services (parse/normalize/match/validate/approve/recalc) plus
interfaces for scheduled jobs, new-match & updated-scorecard detection, source identifiers,
deduplication, review-required vs authorised-automatic modes, and offline catch-up. The discovery
engine itself is **not** built in Phase 8.

## 10. Formats needing verified sample data

- **PlayHQ**, **Play-Cricket**: interface-ready; native adapters pending a legitimate sample export
  to verify structure. Documented, not claimed.
- Generic CSV/Excel/JSON/XML are covered by the mapping-template engine in the interim.

## 11. Testing (STEP 12)

Per-adapter: valid & malformed files, missing fields, partial scorecards, conflicting records,
captain/keeper/toss mapping, dismissal codes, aliases, ambiguous players, duplicate matches,
identical re-import, approval + recalc integration, interrupted/resumed imports, workspace isolation,
permissions, rollback/recovery. The existing CricketStatz regression suite must stay green. Realistic
fixtures + deterministic sample datasets. Backend + frontend + integration + build each run.

## 12. Staged implementation plan

- **8.1 Adapter core & CCDM.** Define the contract, registry, and CanonicalDataset; move the shared
  stage→match→validate→commit flow onto the CCDM. No behaviour change.
- **8.2 CricketStatz as adapter.** Refactor `domain/imports.py` behind the contract; all existing
  import tests green (regression lock).
- **8.3 Generic mapping engine + CSV adapter.** Mapping templates; column→CCDM; preview/validation.
- **8.4 Excel + JSON + XML adapters.** Reuse the mapping engine.
- **8.5 Duplicate detection service.** Confidence scoring; exact vs possible; review actions.
  **R1:** attach a new source to an existing match (`match_source`), retaining conflicts for review.
- **8.6 Universal Import Wizard.** Source upload → format detect → workspace → review entities →
  identity match/create → scorecard review → preview → confirm → results + Import History. Surfaces
  **R1** conflicting-source review.
- **8.7 Import history & provenance UI.** Checksums, batch history, scorecard→source tracing, and the
  **R1** multiple-sources-per-match view.
- **8.8 Resumable/batch imports & error handling.** **R2** recovery on promotion + staging; **R3**
  memory-efficient streaming/chunked processing.
- **8.9 Phase 9 service interfaces.**
- **8.10 Comprehensive tests, docs & Phase 8 acceptance checklist.** Includes **R2** interruption/
  recovery tests (parse, stage, promote) and **R3** large-dataset performance benchmarks (thousands
  of matches) with recorded results.

Each stage: implement → test (backend/frontend/integration/build) → fix defects → commit → continue
without routine approval. Pause only for significant architectural conflict, destructive change,
security, or substantial scope change.
