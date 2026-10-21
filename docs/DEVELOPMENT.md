# OneStats — Development Guide (Phase 2 Foundation)

This is the foundation build: a Tauri desktop shell, a FastAPI backend, and a PostgreSQL
migration framework. **No cricket-domain features yet.** Phase 1 planning docs in this
folder are the source of truth.

## Prerequisites (already provisioned)

Node.js 24 LTS · Python 3.12 · Rust + Cargo (MSVC) · Microsoft C++ Build Tools ·
WebView2 · Git · PostgreSQL 17 (service, `localhost:5432`, database `onestats`, app role
`onestats_app`).

## One-time setup

```bash
# from the repo root (Git Bash)
scripts/dev.sh backend-install     # Python venv + backend deps
scripts/dev.sh desktop-install     # npm deps for the desktop app
cp services/api/.env.example services/api/.env   # then set ONESTATS_DB_PASSWORD
```

> **Secrets:** the `onestats_app` password goes only in `services/api/.env` (gitignored)
> or the environment. It is never committed, logged, or placed in source.

## Everyday commands

| Command | What it does |
|---|---|
| `scripts/dev.sh backend` | FastAPI backend (auto-reload) on `http://localhost:8000` |
| `scripts/dev.sh desktop` | Desktop app (`npm run tauri dev`) — native window |
| `scripts/dev.sh desktop-web` | Web frontend only (Vite) on `http://localhost:1420` |
| `scripts/dev.sh test` | Backend (pytest) + frontend (vitest) tests |
| `scripts/dev.sh lint` | Backend ruff + frontend `tsc --noEmit` |
| `scripts/dev.sh build` | Build the Windows desktop app (Tauri bundler) |
| `scripts/dev.sh migrate` | Apply DB migrations (needs the DB credential) |
| `scripts/dev.sh stop` | Stop dev servers on ports 8000 and 1420 |

Equivalent raw commands (if you prefer): backend — `cd services/api && .venv/Scripts/python
-m uvicorn onestats.main:app --reload`; frontend — `cd apps/desktop && npm run tauri dev`.

## Desktop ↔ backend interface

The desktop app talks to the backend over local HTTP. The base URL defaults to
`http://localhost:8000` and is overridable with `VITE_ONESTATS_API_URL`. The typed client
lives in `apps/desktop/src/lib/api.ts`. Health endpoints:

- `GET /api/v1/health` — liveness (no DB needed)
- `GET /api/v1/health/db` — readiness (reports DB configured/connected)

## Process management (development vs packaged)

- **Development:** the backend and the desktop app are started independently (two
  commands above). This keeps iteration fast and the Rust rebuild decoupled from backend
  changes.
- **Packaged app (future):** the FastAPI backend will be bundled and supervised by the
  Tauri shell (e.g. a PyInstaller sidecar). **This production process-management design is
  not finalised** (`[DECISION D7]`, deliverable 37) and is intentionally deferred.

## Database & migrations

The app connects as the least-privilege `onestats_app` role using the credential from the
environment. Migrations (Alembic) resolve the URL from settings — they **refuse to run**
without a configured credential (no blind connection). Apply with
`scripts/dev.sh migrate`. The v1 foundation migration creates `workspace`, `app_user` and
`audit_log` (with a Row-Level Security scaffold) — **no cricket-domain tables**. The
existing database is never reset or overwritten.

## Tests

- Backend: `services/api/tests` (pytest) — config, health, error envelope, DB-not-configured.
- Frontend: `apps/desktop/src/**/*.test.ts` (vitest) — navigation invariants.
- Live verification (foundation): backend starts, `/health` responds, the desktop app
  renders the six sections, light/dark themes toggle, and the Dashboard fetches the
  backend version over HTTP.
