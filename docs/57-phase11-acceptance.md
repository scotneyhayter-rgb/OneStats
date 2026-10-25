# Phase 11 — Media Archive & OneVault Integration: Manual Acceptance Checklist

For a reviewer in the **OneStats Sandbox**. The Media Archive is reached from **Club Management → Media
Archive** (`/manage/media`). Sign in as a user with `media.manage` (Super/Workspace Admin have it).
Record each test **Pass / Fail / Blocked**.

## Scope of live sources (read first)

OneStats works **fully on internal storage**. **OneVault is optional and NOT operational** — its adapter
is capability-detected and reports *unavailable* until a verified OneVault API is configured; it is never
marked operational, and the separate OneVault application is never modified. External references point at
files OneStats does not own and are never fetched/modified/deleted by OneStats.

## Checklist

1. **Open the Media Archive.** Club Management → Media Archive. Three tabs show: Library, Heritage
   Collection, Storage & Integrity.
2. **Storage providers.** Storage & Integrity tab → confirm **internal** is *available* + *default*,
   **external** *available*, **onevault** *unavailable* (with the reason). Nothing claims OneVault works.
3. **Upload an original.** Library → choose a Kind, optional Title → **Choose file to upload** (a JPEG/
   PNG/TIFF/PDF). Confirm "Media uploaded." and the item appears with a thumbnail (for images) and its
   size.
4. **Original preserved.** Confirm the original is kept at original quality (the thumbnail is a separate
   derivative). Re-uploading the same file reports it as a duplicate (detected, not blocked).
5. **Copyright + publication control.** On an asset, enter a copyright value → **Save**. Then **Mark
   publishable**. Confirm you cannot mark it publishable with no copyright recorded, and that marking it
   **junior** (or sensitive) prevents publication — internal access never implies publication rights.
6. **Junior/private protection.** Toggle **Mark junior** on an asset and confirm it cannot be made
   publishable while protected.
7. **Archive integrity.** Storage & Integrity → **Verify archive**. Confirm the report shows Total /
   Verified OK / Missing / Checksum-fail counts from real files (0 missing / 0 fail on a healthy archive).
8. **Club Heritage Collection.** Heritage Collection → create a collection (e.g. "RMCC Heritage") →
   **Open** it → choose a media item + enter its **historical significance** → **Add to collection**.
   Confirm the item is listed with its significance marker.
9. **Heritage publication is controlled.** Confirm a heritage item can only be made publication-eligible
   when its underlying asset is itself cleared for publication (nothing published by default).
10. **Stable identifiers / migration (reviewer/API).** An asset's links use its stable id, so migrating
    its storage never breaks references. Migration (`POST /assets/{id}/migrate`) verifies checksums and
    rolls back on failure; this is covered by automated tests (migrating to the unavailable OneVault
    fails gracefully, leaving the asset unchanged).
11. **External reference.** Register an external reference (`POST /assets/external`, or via a future UI
    control) and confirm OneStats stores only the reference and never fetches/deletes the external file.
12. **Reuse Phase 10 research documents.** A research source document can be promoted into a single
    canonical media asset (`POST /media/from-research-source/{id}`) — the file is moved (no duplicate),
    the research source points at the asset, and the document viewer still works. Covered by automated
    tests.
13. **Workspace isolation & permissions.** Media is confined to its workspace (FORCE RLS); all media
    actions require `media.manage`, enforced server-side (not just by hiding controls).
14. **Backup manifest (reviewer/API).** `GET /media/backup/manifest` returns a validatable manifest
    (assets + checksums + relationships + heritage) and `GET /media/backup/verify` detects missing/
    corrupted files — the basis for secure backup/restore with relationship preservation.
15. **Regression.** Confirm Phase 7–10 still work (approvals, provenance, research, statistics) — the
    automated regression suite is green.

## Automated coverage (last run)

| Suite | Result |
|---|---|
| Backend (pytest) | **512 passing, 2 skipped** |
| Desktop (vitest) | **60 passing**; `tsc` clean; ruff clean |
| Regression | Phase 7 approval/recalc/stat, Phase 8 import, Phase 9 AutoSync, Phase 10 research — green |

New Phase 11 tests: providers (round-trip, traversal, OneVault unavailable), assets (originals preserved
+ thumbnails, duplicate detection, external not-fetched, publication guards, stable-id links, isolation),
migration (stable-id + verify + rollback, corruption not migrated, OneVault graceful), heritage (items +
publication requires cleared asset), backup (missing/mismatch detection, manifest, restore check),
integration (promote moves file no-duplicate, idempotent).

**Phase 11 implementation + automated tests complete — awaiting user acceptance. Do not commence Phase 12
without formal Phase 11 acceptance.**
