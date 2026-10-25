# Phase 11 — Media Archive & OneVault Integration: Implementation Report

**Status:** implementation + automated tests complete (2026-10-25) — **awaiting user acceptance.**
Manual acceptance checklist: [57](57-phase11-acceptance.md). Design refs: media archive
[20](20-media-archive.md); OneVault contract [21](21-onevault-integration-contract.md).

Phase 11 adds a Media Archive that preserves original scorecard images, photographs and documents at
original quality, behind one storage abstraction with three providers, keyed by a stable media id —
OneStats works fully without OneVault.

## Requirements coverage (the 15 mandatory items)

1. **Works without OneVault; internal default** ✅ — internal provider is the default; OneVault optional.
2. **Three providers, one interface** ✅ — `MediaStorageProvider` with InternalStorage / OneVault /
   ExternalReference (`domain/media/providers.py`).
3. **Stable media ids** ✅ — `media_asset.id` is the stable identifier; links (`media_link`) point at it,
   so moving a file never breaks references to matches/players/research/heritage.
4. **Originals preserved; derivatives separate; no auto-delete/modify** ✅ — originals stored
   byte-for-byte; thumbnails/previews generated separately; nothing auto-deletes an original.
5. **Secure audited migration (checksum, recovery, rollback)** ✅ — `migration.py`: integrity pre-check,
   target verify, rollback on failure, source removed only after verification; all audited.
6. **OneVault capability detection; no invented APIs; app untouched** ✅ — `OneVaultProvider` reports
   unavailable until a verified API is configured; never fabricates an API; OneVault app never modified.
7. **Reuse/extend Phase 10 source infrastructure; no duplicates** ✅ — `integration.promote_research_source`
   moves a research document into one canonical asset (no duplicate files/records/libraries).
8. **Club Heritage Collection** ✅ — `heritage_collection` + `heritage_item` with significance markers,
   descriptions and permission-controlled publication eligibility.
9. **Private/junior protection** ✅ — `junior_protected` / `sensitive` flags + `media.manage` permission;
   protected media can never be made publishable.
10. **Copyright/licensing/attribution/provenance; internal ≠ publish** ✅ — recorded per asset;
    publication is an explicit, guarded decision.
11. **Secure backup/restore (checksum, missing-file detection, relationships)** ✅ — `backup.py`:
    verify_media, build_manifest, check_restore.
12. **Extensible for future One-family software** ✅ — the stable-id + adapter + capability-detection
    pattern is the template; no unnecessary dependencies.
13. **Tests across providers/migration/integrity/isolation/relationships/recovery** ✅ — see below.
14. **Practical for non-technical volunteers** ✅ — guided uploads, thumbnail previews, plain-language
    actions, clear organisation and integrity check.
15. **Preserve Phase 7–10 functionality + regression** ✅ — full regression green.

## Automated test results

- Backend **512 passing, 2 skipped**; Desktop **60 passing**; `tsc` clean; `ruff` clean.
- Regression green: Phase 7 (approval/recalc/stat), Phase 8 (import), Phase 9 (AutoSync), Phase 10
  (research) all passing.

## Storage providers & supported media

- **Internal** (default) — OneStats-managed, workspace-partitioned, traversal-guarded; originals
  preserved. **External reference** — a pointer OneStats never fetches/modifies/deletes. **OneVault** —
  optional, capability-detected, **not operational** (no verified API).
- Media types: JPEG, PNG, TIFF, WebP, GIF images and PDF (30 MB default cap); thumbnails/previews derived
  for images.

## Known limitations & external dependencies

- **No verified OneVault API** — the OneVault provider stays interface-only until a real API is confirmed
  and marked verified; it is never claimed operational. This is the single external dependency and does
  not block any media feature.
- Thumbnails are generated for image types; PDF page-thumbnails are not rendered in this phase (the PDF
  original is preserved and served).
- Mobile upload (deliverable 20a) is coordinated with Phase 16 and is **not** built here.
- Backup produces a validatable manifest + integrity verification; scheduling and off-site copy are an
  operational concern (deliverable 32), not built in this phase.

## Manual acceptance instructions

See [57](57-phase11-acceptance.md): 15 guided tests in the Sandbox (open archive, providers, upload,
originals preserved, copyright + publication control, junior protection, integrity verify, heritage
collection + controlled publication, stable-id migration, external reference, Phase 10 reuse, isolation/
permissions, backup manifest, regression).

## Readiness for Phase 12

Media panels and stable ids are available for the statistics phase to reference. **Do not commence
Phase 12 without formal Phase 11 acceptance.**
