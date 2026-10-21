# OneStats

**Cricket Statistics Made Simple** — a professional cricket statistics, historical-research
and records-management desktop application. Part of the **One** software family.

> **Status: Phase 2 — Windows Desktop & Server Foundation** (in progress).
> Phase 1 (planning & architecture) is complete and is the source of truth: see
> [`docs/`](docs/README.md). This phase builds the foundational skeleton only — **no
> cricket-domain business logic yet**.

## Architecture (foundation)

```
Tauri 2 desktop (React + TS + Tailwind + shadcn/ui)
        │  local HTTP (localhost)
        ▼
FastAPI backend (Python 3.12)  ──►  PostgreSQL 17 (role: onestats_app)
```

See [`docs/02-technical-architecture.md`](docs/02-technical-architecture.md).

## Repository layout

```
OneStats/
├─ apps/
│  └─ desktop/        # Tauri + React desktop client
├─ services/
│  └─ api/            # Python FastAPI backend
├─ docs/              # Phase 1 planning documents (source of truth)
├─ scripts/           # dev helper scripts
└─ PHASE1_MASTER_PROMPT.md
```

## Development

See [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) for full setup. Quick reference:

| Task | Command |
|---|---|
| Install backend deps | `scripts/dev.sh backend-install` |
| Start backend | `scripts/dev.sh backend` |
| Install desktop deps | `scripts/dev.sh desktop-install` |
| Start desktop (dev) | `scripts/dev.sh desktop` |
| Run tests | `scripts/dev.sh test` |
| Lint / format check | `scripts/dev.sh lint` |
| Build Windows app | `scripts/dev.sh build` |

> **Secrets** (the `onestats_app` DB password, etc.) are read from a gitignored `.env`
> (copy `.env.example`). Never commit secrets. The database is never exposed to the
> public internet.

## Licence

Commercial. © 2026. All rights reserved.
