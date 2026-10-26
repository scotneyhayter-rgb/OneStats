# 71. Phase 16 Follow-ups — Member Portal, Ask-on-Portal, Mobile Upload

**Implemented 2026-10-26.** Delivers the three follow-ups the Phase 16 report
([65](65-phase16-report.md)) deferred: an **authenticated member portal view**, **Ask OneStats on the
portal**, and **mobile media upload** (deliverable [20a](20a-mobile-upload-architecture.md)).

> No phase is marked user-accepted. Automated tests are development assurance; manual acceptance stays in
> the deferred register ([62](62-deferred-acceptance-register.md)).

## 1. Authenticated member portal view

`GET /api/v1/workspaces/{workspace_id}/portal` (gated by `match.view`) — the members' read-only index: the
club's **public** published items **plus** the non-public catalogue (unpublished drafts) a member is
permitted to see, each flagged `public` / members-only, with counts and the club branding. Revoked items
never appear. Runs under the workspace transaction, so RLS scopes it to the member's workspace.

Desktop: **Club Management → Member Portal** (`features/portal/MemberPortal.tsx`) — searchable, badges each
item public / members-only, opens published snapshots.

## 2. Ask OneStats on the portal

The member portal response carries `ask: { enabled, endpoint }` — `enabled` when the member holds
`ask.query`. The desktop Member Portal embeds a read-only **Ask** box that calls the existing deterministic
Ask endpoint (`/workspaces/{id}/ask`). Numbers always come from the one engine; nothing is fabricated, and
qualifications travel with each answer. No new query path — it reuses Phase 14.

## 3. Mobile media upload (deliverable 20a)

A QR/paired, short-lived, scoped upload path so authorised users upload photos/PDFs from a phone into the
media review queue — without a desktop — using the Windows app to pair.

- **Pairing** (`/workspaces/{id}/mobile-upload/*`, gated `media.manage`): start / list / revoke sessions.
  Creating one returns the **raw token once** plus the relative upload path; the desktop composes the LAN
  URL + QR. Only the token's **SHA-256 hash** is stored (never the token), sessions are time-limited
  (default 30 min, max 240), revocable, and audited.
- **Upload** (`/upload/{workspace_id}/{session_id}`, token via `X-Upload-Token`, **not** a bearer session):
  the phone posts files; no long-lived credential lands on it. The workspace comes from the paired URL so
  RLS scopes the session lookup; the token proves the pairing.
- **Pipeline**: files are **content-verified** (magic-byte sniff, not just the declared type) against an
  allowlist (PNG/JPEG/WebP images via Pillow + PDF), size-limited (`max_media_bytes`), stored as preserved
  originals via the media archive, marked `source_provenance=mobile_upload`, `visibility=private`, and left
  **unassigned** so they enter the media review queue. Nothing is auto-published; any extracted statistics
  still require human verification before official records.
- Desktop: a **"Upload from a phone"** card on Media Archive → Library starts/revokes sessions and shows the
  one-time code + path.

### Security & isolation

Token hashed at rest and never logged; short TTL; scoped and revocable; per-workspace FORCE RLS
(`upload_session`, migration 0056). The dev server still binds `127.0.0.1`; **LAN binding + TLS on the LAN
and QR rendering remain an operator/release step** (not auto-enabled), consistent with 20a §20a.7.

## Code map

- `db/migrations/versions/0056_upload_session.py` — RLS-isolated pairing sessions.
- `domain/mobile_upload.py` — sessions, token hashing/resolution, content-verified `accept_upload`.
- `api/v1/mobile_upload.py` — pairing router (`media.manage`) + token-auth upload router.
- `domain/publishing.py::member_portal`, `api/v1/portal.py` — authenticated member view + Ask pointer.
- `apps/desktop/src/features/portal/MemberPortal.tsx`, `features/media/MediaArchive.tsx` (pairing card),
  `app/navigation.ts` (Member Portal), `lib/api.ts`.

## Automated coverage

- `tests/test_mobile_upload.py` (9): one-time token hidden in listings + hashed at rest, correct/wrong
  token, expiry + revocation, image stored unassigned for review, PDF accepted / unknown type rejected,
  size limit, **workspace isolation**, route wiring + token auth.
- `tests/test_publishing.py::test_member_portal_includes_non_public_items`.
- `features/portal/member-portal.test.tsx` (2): public/members-only flags; embedded Ask queries the engine.

Backend regression after this work: **635 passed, 2 skipped**. Frontend: 74 passed; typecheck clean.

## Still outstanding (unchanged, needs the user)

A polished standalone hosted portal app and public reachability depend on the **hosting decision** (static
vs central service); LAN binding/TLS + QR rendering are release/operator steps; remote (cloud) upload is a
later release per 20a §20a.9.
