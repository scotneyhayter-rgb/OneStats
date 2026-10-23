# OneStats — Phase 2 Completion Report

**Phase 2 — Windows Desktop & Server Foundation** · 2026-10-22
Branch: `phase-2-foundation` · builds on the Phase 1 planning docs (unchanged).

> Foundation only. No cricket-domain business logic, no authentication system, and the
> Cricket Statz dataset was **not** imported into any database.

## 1. Implemented features

**Desktop (Tauri 2 + React 19 + TS + Tailwind v4 + shadcn-style UI)**
- Native Windows Tauri shell (`productName` OneStats, 1280×832 window, min size).
- Six approved primary sections (Dashboard, Matches, People, Statistics, Ask OneStats,
  Settings) via HashRouter; Matches/People/Statistics/Ask/Settings are clearly-labelled
  **foundation placeholders** (not faked functionality).
- Dashboard shows **live backend + database status** fetched over HTTP.
- Light/dark themes (toggle persisted to `localStorage`, `prefers-color-scheme` aware);
  neutral design-token system, **workspace-branding-ready, no hardcoded RMCC branding**.
- Application version display (v0.1.0, Phase 2 — Foundation).
- Consistent Loading / Empty / Error states; accessible keyboard focus + ARIA.
- Typed desktop→backend client (`apps/desktop/src/lib/api.ts`).

**Backend (Python 3.12 + FastAPI + Pydantic)**
- App factory with startup/shutdown lifespan; API **v1** versioning (`/api/v1`).
- `/api/v1/health` (liveness) and `/api/v1/health/db` (DB readiness).
- Env-based configuration (pydantic-settings); **DB password only from env/.env**.
- Structured logging (secret-safe); consistent JSON **error envelope**; input validation;
  CORS limited to the local desktop origins.
- SQLAlchemy engine + safe connectivity check (no credentials in logs).

**Database (PostgreSQL 17 + Alembic)**
- Alembic tooling resolving the URL from settings (never hardcoded); **refuses to run
  without a configured credential**.
- v1 foundation migration: `workspace`, `app_user`, `audit_log` (+ workspace_id index)
  with a **Row-Level Security scaffold** (policy keyed on a per-session GUC). **No
  cricket-domain tables.**

**Developer experience**
- `scripts/dev.sh` (install / backend / desktop / desktop-web / test / lint / build /
  migrate / stop) + `docs/DEVELOPMENT.md`.

## 2. Files created (principal)

```
.gitignore, README.md
services/api/pyproject.toml, .env.example, alembic.ini
services/api/onestats/{__init__,main}.py
services/api/onestats/core/{config,logging,errors}.py
services/api/onestats/db/{base,session}.py
services/api/onestats/db/migrations/{env.py,script.py.mako,versions/0001_foundation.py}
services/api/onestats/api/v1/{health,router}.py
services/api/tests/{conftest,test_health,test_config}.py
apps/desktop/  (Tauri scaffold) + src/{main,App}.tsx, index.css
apps/desktop/src/app/{navigation.ts,navigation.test.ts}
apps/desktop/src/lib/{utils,theme,api,version}.(ts|tsx)
apps/desktop/src/components/{ui/button,ui/card,layout/*,states/States}.tsx
apps/desktop/src/features/{Dashboard,Placeholder,sections}.tsx
scripts/dev.sh, docs/DEVELOPMENT.md, docs/PHASE2_COMPLETION_REPORT.md
```

## 3. Commands used

`git init/add/commit` · `python -m venv` + `pip install -e ".[dev]"` · `pytest` · `ruff
check --fix` · `alembic upgrade head --sql` (offline) · `npm create tauri-app@latest` ·
`npm install` · `npm run build` · `npm run test` · `uvicorn onestats.main:app` ·
`cargo build` (native). Full list in `docs/DEVELOPMENT.md`.

## 4. Tests executed and their results (actual)

| Check | Command | Result |
|---|---|---|
| Backend unit/integration | `pytest -q` | **11 passed** (7 + 4 config) |
| Backend lint | `ruff check` | **clean** (0 issues) |
| Migration compiles | `alembic upgrade head --sql` | **exit 0** (valid SQL generated) |
| Migration safety guard | `alembic upgrade head` (no creds) | **refused** with a clear message (exit 1, by design) |
| Frontend build | `npm run build` (tsc + vite) | **success** — `dist/` produced, 1590 modules |
| Frontend tests | `npm run test` (vitest) | **3 passed** |
| Backend starts + health | `uvicorn` + `curl /api/v1/health` | **HTTP 200** |
| Desktop renders 6 sections | browser preview of the Vite app | **verified** (screenshots) |
| Light/dark themes | theme toggle | **verified** — both render |
| Desktop↔backend comms | Dashboard fetch of `/api/v1/health` | **verified** — "OneStats API v0.1.0 (development)" shown live |
| DB-not-configured handling | Dashboard DB status | **verified** — shows "not configured", no crash |
| Secrets excluded from VCS | `git diff --cached` scan | **verified** — no `.env`/node_modules/target/.venv/dist staged |
| **Native Tauri build** | `cargo build` | **success** — compiled in 4m24s, produced `desktop.exe` (12.8 MB) |

_No test was marked passed without being executed._

## 5. Remaining issues / not yet done

- **DB credential unavailable:** the `onestats_app` password is not in the environment, so
  the migration was **not applied to the live `onestats` database** and live DB connectivity
  is **unverified**. Action: set `ONESTATS_DB_PASSWORD` in `services/api/.env`, then
  `scripts/dev.sh migrate` and re-check `/api/v1/health/db`.
- **Native Tauri compile:** first Rust build is heavy; status in §7.
- Benign deprecation warning from Starlette's TestClient (httpx) — cosmetic.

## 6. Security concerns / notes

- **Secrets:** only via env/.env (gitignored); none in code, logs, or Git (verified). DB
  password never logged; connection errors log the error class only.
- **No authentication system** was built (deliberate — not faked).
- **RLS scaffold** is enabled with a policy but not `FORCE`d; because the app role owns the
  tables, full enforcement needs `FORCE ROW LEVEL SECURITY` (and the data-access layer that
  sets the session workspace GUC) — planned for Phase 3 (deliverable 6).
- **Tauri CSP** is `null` (scaffold default) — tighten before any release.
- Dependencies are current/bleeding-edge (React 19, Vite 8, Tailwind v4, TS 6); `npm audit`
  reported **0 vulnerabilities**.

## 7. Native Tauri build status

**Success.** `cargo build` for `apps/desktop/src-tauri` compiled the full native app in
**4m 24s** (first build; downloaded + compiled all Tauri/wry/WebView2 crates), producing
`apps/desktop/src-tauri/target/debug/desktop.exe` (~12.8 MB). The Windows desktop app
therefore builds natively end-to-end. `npm run tauri dev` launches it as a native window.

> Minor cosmetic note: the Rust package/binary is still named `desktop` (from the
> scaffold), while the Tauri `productName` and window title are **OneStats**. Renaming the
> Cargo package to `onestats-desktop` is a safe polish item for early Phase 3.

## 8. Decisions — resolved in the Phase 2 review (2026-10-23)

1. **Toolchain** (React 19 / Vite 8 / Tailwind 4 / TS 6) — **accepted provisionally**,
   subject to compatibility checks + passing tests (all green). `[D-toolchain]`
2. **RLS enforcement** — adopt **`FORCE ROW LEVEL SECURITY` + transaction-scoped (`SET
   LOCAL`) workspace context** in Phase 3. `[D2a]`, deliverable 6 §6.7.
3. **Migration vs runtime role** — adopt a **migrator/owner role for DDL** and a
   **non-owner runtime `onestats_app`** (DML only, always RLS-bound). `[D24]`, deliverable
   6 §6.7. (Creating the migrator role needs a superuser — a Phase 3 user action.)
4. **Packaged backend process management** — documented (loopback-only ephemeral port, shell
   lifecycle binding, local token handshake, OS credential store, health supervision);
   final packaging still deferred `[D7]`. Deliverable 31 §31.3a.
5. **Desktop CSP** — current `null` **recorded as a development-only limitation**;
   restrictive production CSP + least-privilege Tauri capabilities planned. `[D23]`,
   deliverable 33 §33.5a.
6. **Git identity** — **left unchanged** (local `Scotney Hayter
   <scotney.hayter@gmail.com>`) per instruction; will not change without explicit approval.
7. **Mobile image/document uploads** — new confirmed requirement; architecture in
   [20a](20a-mobile-upload-architecture.md) `[D22]`; Phase 2 foundational accommodations
   noted (20a §20a.8), nothing later-phase built.

## 8a. Live database verification — COMPLETE ✅ (2026-10-23)

Performed with Option B (separate `onestats_migrator` owner + non-owner `onestats_app`
runtime). No passwords shown/committed; no database reset; no data left behind.

- **PostgreSQL security:** service running; `pg_hba.conf` all `scram-sha-256` (local +
  127.0.0.1 + ::1, incl. replication), **no `trust`**; wrong admin password **rejected**;
  runtime `password_encryption = scram-sha-256`.
- **Roles:** `postgres` superuser (admin); **`onestats_app` and `onestats_migrator` both
  non-superuser, no BYPASSRLS, no CREATEROLE/CREATEDB**.
- **Migration:** applied as `onestats_migrator`; `alembic_version = 0001_foundation`;
  tables `workspace`, `app_user`, `audit_log` (+ `alembic_version`) **all owned by
  `onestats_migrator`**.
- **RLS:** enabled on `audit_log` with policy `audit_log_workspace_isolation`.
- **`onestats_app` least privilege proven live:** authenticates; **DDL denied** (CREATE/
  ALTER/DROP → 42501); authorised **read+write OK**; **RLS denies writes with no workspace
  context and hides rows across workspaces**; all test writes **rolled back** (row counts 0).
- **App↔DB over HTTP:** `/api/v1/health/db` → `database_connected: true`.
- **Secrets:** none in logs; `.env` gitignored and **never committed**; no hardcoded
  secrets in tracked files.

## 9. Readiness for Phase 3

**Phase 2 is now fully verified, including the live database** (§8a). The foundation —
desktop shell + six-section nav + themes, FastAPI backend (health/config/logging/errors),
Alembic + applied v1 migration with the migrator/runtime role split and RLS, dev workflow,
and all tests + builds green — is complete. **Phase 3 (Workspaces, Onboarding & User
Permissions)** can begin on approval. Carry-over for early Phase 3: apply `FORCE ROW LEVEL
SECURITY` + transaction-scoped workspace context (D2a) when domain tables land; tighten the
Tauri CSP/permissions (D23). **Phase 3 has not been started.**
