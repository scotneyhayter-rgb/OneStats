# PlayHQ Connector — Implementation Report

**Date 2026-10-26.** PlayHQ (RMCC's live scoring platform) was the long-standing gated external
dependency. With PlayHQ's integration guide now provided (organisation id, tenant, and the cricket API
flow), the connector has moved from **interface-only** to **implemented — needs the API key + live
response validation**. Nothing is fabricated: without a key it refuses to fetch.

## What was implemented

- **`domain/autosync/playhq.py`** — a real `PlayHQConnector` (SyncSource) + `PlayHQClient`:
  - Documented flow: organisation → **Seasons** (`/v1/organisations/{org}/seasons`) → **Grades**
    (`/v1/seasons/{season}/grades`) → **Grade Fixture** (`/v2/grades/{grade}/fixture`, cricket), mapping
    each game to the standard match-summary row and feeding the existing staging → validation → identity-
    match → preview → approval pipeline (no auto-approval by the connector).
  - Auth headers `x-api-key` + `x-phq-tenant` (`ca`); cursor pagination via `metadata.hasMore`/`nextCursor`.
  - **Defensive, isolated mapping** (`_game_to_row`, `_result_text`): tries several likely field names and
    treats anything missing as **unknown**, never guessed — so an unresolved result imports as draft for
    review rather than a fabricated outcome.
- **Config:** `playhq_org_id` (defaults to the RMCC org `2a9c6833-92cb-466b-aea8-16fa8277887d`),
  `playhq_tenant` (`ca`), `playhq_base_url` (`https://api.playhq.com`), `playhq_api_key` (entered later).
- **Catalogue:** PlayHQ is now registered as a live connector with status **`needs_credentials`** (not
  interface-only); AutoSync will use it once a key is configured, and reports clearly if the key is missing.

## Live validation attempt (2026-10-26)

With the credentials from PlayHQ's email entered (API key in the gitignored `.env`, tenant `ca`, org
`2a9c6833-…887d`), the **region-specific CA host** was identified and fixed: Cricket Australia uses
**`https://api.caprod.playhq.com`** (not the generic `api.playhq.com`), so the host is now derived from the
tenant (`host_for_tenant`: ca → caprod, eu → euprod, else api.playhq.com).

A read-only call to `/v1/organisations/{org}/seasons` on the CA host returned **HTTP 401
`{"message":"Client ID is Invalid"}`** for both `ca` and `CA` tenant casings. The request reached the right
endpoint and PlayHQ validated the header — so the **connector, host, headers and endpoint are correct**, but
the **API key is being rejected**. The key value matches the email exactly (verified), so the likely cause
is that the newly-issued key is **not yet active / not yet enabled for the public API on PlayHQ's side**
(the email was sent earlier the same day). No further live calls were made (to respect rate limits/ToS).

**Action for the user:** confirm with PlayHQ that the Client ID (`47527697-…`) is active and authorised for
the public API for this organisation, or re-issue it; once it authenticates, the connector is ready to run
(the response field mapping should still be validated against the first live responses).

## What remains (needs your input / a real key)

- **Enter the PlayHQ API key** (`PLAYHQ_API_KEY`, the Client ID UUID). Stored per PlayHQ's docs; OneStats
  reads it from config/environment (and the Windows Credential Manager in a packaged install, deliverable 33).
- **Validate the response field mapping against live cricket (v2) responses.** The exact v2 cricket JSON
  field names are gated at `docs.playhq.com/tech`; the mapping is provisional and defensive until confirmed
  with real payloads. First live run should be reviewed before enabling authorised auto-approval.
- **Confirm the exact v2 fixture/ladder/game-summary paths** against the gated docs (the v1 seasons/grades
  paths are confirmed; the v2 paths follow the documented pattern and are easy to adjust in one place).
- **Review PlayHQ's Terms of Service** for the integration before production use.

## Tests

`tests/test_playhq_connector.py` (5): traversal + mapping (with a fake client — **no live calls**),
defensive field extraction, unknown-result-not-guessed, missing-key refuses to fetch, cursor pagination.
`tests/test_autosync_sources.py` updated (PlayHQ is now `needs_credentials`, still can't fetch without a
key). No live PlayHQ API calls are made by the test suite.
