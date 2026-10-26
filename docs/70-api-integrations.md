# 70. Workspace API & Integrations Management

**Implemented 2026-10-26.** Clubs and associations manage their own external-provider API credentials from
**Workspace Settings → API & Integrations** — no configuration-file or source-code edits are required. This
is the reusable, secure credential-management foundation shared by the Phase 8–9 import & AutoSync
framework.

> **No phase is formally user-accepted until the user approves it.** The automated tests below are
> development assurance; the manual acceptance tests are recorded in
> [62-deferred-acceptance-register.md](62-deferred-acceptance-register.md).

## What it does

From one screen, a workspace administrator can:

- **View supported integrations** and each provider's configuration schema (which fields are secret, which
  are plain config).
- **Add / configure** a provider credential with provider-specific fields (e.g. PlayHQ API key + organisation
  id + tenant).
- **Test connectivity** — a real authenticated request is made; a connection is only reported *Connected*
  after it actually succeeds. Nothing is assumed working.
- **Enable / disable** an integration without deleting it.
- **Rotate** the secret (replace it) securely.
- **Revoke** a credential — the stored secret is destroyed.
- **See health** — last test result + time, last success — and **integration audit history**.

## Security model (how the mandatory constraints are met)

| Requirement | How it is implemented |
|---|---|
| Encrypt stored API secrets with a managed key | Secrets are encrypted with **Fernet / MultiFernet** (`core/crypto.py`) before storage. |
| Keep encryption keys separate from the database | The key comes from `ONESTATS_ENCRYPTION_KEY` (env / OS keystore) — **never** stored in the DB. A clearly-marked insecure dev key is used only when none is set (warned); production sets a real key. |
| Never display saved secrets in plaintext | No endpoint or UI ever returns the secret. Reads return masked status only (`has_secret`). The UI shows "Secret stored securely (hidden)". |
| Never include credentials in logs/errors/exports | Audit payloads and test messages carry no secret; errors are sanitised to the exception type. |
| Backend-only credential handling | Decryption happens only on the server, only to make a provider request (`get_secret`, `bind_connector`). |
| Role-based permissions | Endpoints require **`import.configure`** ("Configure import connectors"), held by workspace/super admins; backend-enforced. |
| Secure credential rotation | `rotate` re-encrypts a new secret under the current key; `core/crypto.rotate` re-keys existing ciphertext for key rotation. |
| Audit create / replace / revoke | Every action writes to the workspace `audit_log` (`integration.credential.*`). |
| Protect against SSRF / internal access | Custom endpoints are validated by `core/net.validate_public_url` — https-only, no credentials-in-URL, and the resolved host must be a **global** address (private/loopback/link-local/reserved refused). Built-in providers use fixed, vetted hosts. |
| Preserve security across backups/restores | Secrets are ciphertext in the DB; a backup is useless without the separately-held key, and restores decrypt normally once the key is present. |

### Workspace isolation

Credentials live in `workspace_credential`, which has PostgreSQL **FORCE ROW LEVEL SECURITY** keyed on the
per-transaction `onestats.workspace_id` GUC. One workspace can never read, test or use another's credentials,
and two workspaces may hold **different** credentials for the **same** provider. No path returns a plaintext
secret to any caller, super admins included. A dedicated **cross-workspace Super-Admin status view** (read-
only status across workspaces, still no secrets) is a documented follow-up — today a Super Admin reads
status per workspace through the same workspace-scoped endpoints.

## Providers & current status

| Provider | Status | Notes |
|---|---|---|
| **PlayHQ** | **Working pending credentials + live validation** | Full connector implemented (region hosts, headers, cursor pagination). Reports `needs_credentials` until a workspace enters an API key. Live cricket-v2 response field mapping still to be validated against real data (see [69-playhq-connector.md](69-playhq-connector.md)). The provided key was rejected (401) and awaits replacement. |
| **Custom API (advanced)** | **Reachability check only** | A user-supplied HTTPS endpoint, SSRF-validated. This performs a connectivity check only — it does **not** imply support for arbitrary undocumented APIs. |
| Other online platforms | Interface-only / awaiting verified access | Listed by the connector catalogue; not yet implemented. |

A provider appearing here is **not** a claim of a verified live connection — that is proven only by a
successful **Test**.

## Import / sync control

When a workspace has stored a credential for a connector's provider, an AutoSync run binds the connector to
that **workspace's own** credential (`integrations.bind_connector`) — decrypted backend-only — instead of any
global/environment configuration. The existing staging → validation → duplicate-detection → preview →
approval pipeline is unchanged: imported matches remain **draft** and only approved statistics count.

## Code map

- `services/api/onestats/core/crypto.py` — Fernet/MultiFernet encrypt/decrypt/rotate; key kept outside the DB.
- `services/api/onestats/core/net.py` — `validate_public_url` SSRF guard.
- `services/api/onestats/db/migrations/versions/0055_workspace_credential.py` — the RLS-isolated table.
- `services/api/onestats/domain/integrations.py` — provider registry, credential lifecycle, `get_secret`,
  `bind_connector`, `test_connectivity`, audit.
- `services/api/onestats/api/v1/integrations.py` — workspace-scoped, `import.configure`-gated endpoints.
- `apps/desktop/src/features/settings/Integrations.tsx` — the management screen
  (Workspace Settings → API & Integrations).

## Automated coverage

- `services/api/tests/test_integrations.py` (28): crypto roundtrip/rotation/tamper, SSRF guard (10 unsafe +
  1 safe), provider registry, credential create/list (masked)/rotate/disable/revoke, backend-only secret
  recovery, **workspace isolation**, same-provider-different-credentials, validation (unknown provider /
  missing secret / SSRF), `import.configure` permission gating, audit for every action, test-connectivity
  record path (stubbed — no live network), `bind_connector` using the workspace credential, and API route
  wiring + auth gating.
- `apps/desktop/src/features/settings/integrations.test.tsx` (3): provider listed as not-configured with the
  secret-stays-hidden assurance; add a credential with the provider's secret + config fields (secret rendered
  as a password input); a configured credential shown *Connected* without revealing the secret, then tested.

Full backend regression after this work: **624 passed, 2 skipped**. Frontend: all suites green; typecheck
clean.
