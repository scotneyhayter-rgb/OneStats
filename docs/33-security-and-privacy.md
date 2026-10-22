# 33. Security and Privacy Requirements

**Deliverable 33 of 38** · §3, §27, §33

Security and privacy requirements across OneStats. Principle: **least privilege,
defence-in-depth, protect private/junior data, never expose the database, audit
everything sensitive.**

## 33.1 Database & credentials (§3 — hard rules)

- The app connects **only** as **`onestats_app`** (non-superuser LOGIN, owns `onestats`).
  The superusers (`postgres`, `scotney`) are **never** used by the app.
- **Never embed plaintext DB passwords** in code, config or logs. Credentials and provider
  tokens live in the **Windows Credential Manager** (via Tauri/`keyring`), fetched at
  runtime.
- PostgreSQL is **never exposed to the public internet**; it listens on localhost
  (co-located with the API) and is reachable only through the API (deliverable 31).
- Row-Level Security enforces workspace isolation at the DB layer (deliverable 6); the app
  role never has `BYPASSRLS`.

## 33.2 AuthN / AuthZ

- Authenticated users; passwords stored only as strong hashes (e.g. Argon2/bcrypt) — the
  app handles its own user auth, never plaintext.
- Role- and permission-based authorization in the service layer on every mutating/
  sensitive path (deliverable 7). UI hiding is cosmetic only.
- Workspace scoping checked before any data access (deliverable 6).
- User deactivation is immediate; audit history retained.

## 33.3 Privacy — junior and private data (§24, §29, §30)

- **Protected by default:** dates of birth, junior status/info, contact details,
  protected research notes. Hidden from Viewers and from public portal/website.
- Age rankings/longevity **never** computed from uncertain birth dates (deliverable 24).
- Published and portal data exclude protected fields unless explicitly cleared and
  permitted (deliverables 29–30).
- Data-subject considerations: a documented process for correction/removal of personal
  data, respecting provenance (corrections tracked, not silently erased).

## 33.4 Audit logging (§12, §27)

Append-only `audit_log` for: verified-record changes, verification state changes, import
approvals, identity merges, research verification, branding changes, user administration,
publishing/withdrawals, cross-workspace (super-admin) actions. Each entry: actor, action,
entity, before/after, workspace, timestamp. Audit records are **not editable**.

## 33.5 External sources & copyright (§13, §15, §17, §28)

- Respect provider copyright, terms and access controls; **never bypass access controls**
  or scrape where prohibited (deliverables 17–18).
- Store source copyright metadata; published outputs respect it (deliverables 19–20, 29).
- Provider tokens in the credential store; rate-limit per terms.

## 33.5a Desktop app hardening — CSP & Tauri permissions `[DECISION D23]`

Recorded per the Phase 2 review:

- **Current state (development-only limitation):** the Tauri Content-Security-Policy is
  `null` (the scaffold default), which is **acceptable for development only** and is logged
  here as a known limitation to remove before any release.
- **Production plan:** ship a **restrictive CSP** (no `unsafe-inline`/`unsafe-eval`; default
  `'self'`; connect-src limited to the local backend origin; no remote script/style) and a
  **least-privilege Tauri capability set** (only the commands/plugins the app actually uses;
  no broad filesystem/shell access). Window/webview permissions are scoped per capability.
- The desktop↔backend channel stays **loopback/LAN only**; the webview never loads remote
  code.

## 33.6 Application security hygiene

- Input validation (Pydantic) on all API inputs; parameterised queries (no string SQL).
- TLS for client↔server (deliverable 31); secure IPC for the Tauri sidecar.
- Dependency scanning and updates; minimal attack surface (no public DB/API).
- Structured logs **without** secrets or full personal data; log access controlled.
- Ask OneStats NLP: if an LLM is used, no private data leaves the environment without
  explicit approval (`[DECISION D16]`, deliverable 28).

## 33.7 Secrets inventory (how each is protected)

| Secret | Storage | Never in |
|---|---|---|
| `onestats_app` DB password | Windows Credential Manager | code, config, logs, backups |
| Provider API keys/tokens (PlayHQ…) | Windows Credential Manager | code, config, logs |
| User password hashes | DB (hashed only) | plaintext anywhere |
| TLS keys | OS secure store / protected dir | repo |
