# 4. Repository Structure

**Deliverable 4 of 38**

A single **monorepo** (`OneStats`) holds the desktop app, backend service, shared
schema/types, publication edge and docs. This keeps a small team's workflow simple and
lets the Tauri build bundle the backend sidecar. *Phase 1 creates none of this code* —
it is the target layout for Phase 2.

> Note: the repo is **not yet initialised** (`git init` pending). Recommend initialising
> in Phase 2 with the structure below and a clean `.gitignore`. This Phase 1 folder
> (`C:\OneProjects\OneStats`) becomes the repo root.

## 4.1 Proposed top-level layout

```text
OneStats/
├─ apps/
│  ├─ desktop/                 # Tauri + React desktop client
│  │  ├─ src-tauri/            # Rust shell: window, updater, sidecar, keychain
│  │  │  ├─ src/
│  │  │  ├─ tauri.conf.json
│  │  │  └─ Cargo.toml
│  │  ├─ src/                  # React + TS UI
│  │  │  ├─ app/               # routing, six primary sections (§4)
│  │  │  ├─ features/          # matches, people, statistics, research, ...
│  │  │  ├─ components/        # shadcn/ui-based shared components
│  │  │  ├─ lib/               # api client (typed), theming, utils
│  │  │  └─ styles/            # Tailwind + branding CSS variables
│  │  ├─ index.html
│  │  ├─ package.json
│  │  └─ vite.config.ts
│  └─ portal/                  # read-only mobile/web records portal (§29)
│     └─ src/
├─ services/
│  └─ api/                     # Python FastAPI backend (the one brain)
│     ├─ onestats/
│     │  ├─ main.py            # app factory, routers
│     │  ├─ core/              # config, security, workspace scoping, audit
│     │  ├─ domain/            # entities: org, people, matches, scorecards
│     │  ├─ stats/             # THE one deterministic statistics engine
│     │  ├─ reports/           # RMCC catalogue + report builder
│     │  ├─ imports/           # connectors (PlayHQ...), Cricket Statz, staging
│     │  ├─ research/          # research centre, discovery jobs
│     │  ├─ media/             # internal store / OneVault / external refs
│     │  ├─ publishing/        # publication cache + read-only API
│     │  ├─ ask/               # Ask OneStats intent→query mapping
│     │  ├─ jobs/              # background worker, scheduler
│     │  └─ db/                # SQLAlchemy models, Alembic migrations
│     ├─ tests/                # pytest (unit + calculation fixtures)
│     ├─ pyproject.toml
│     └─ alembic.ini
├─ packages/
│  ├─ shared-types/            # generated TS types from the OpenAPI schema
│  └─ db-schema/               # ERD source, SQL, seed/reference data (no prod data)
├─ docs/                       # Phase 1 deliverables (this folder) + ADRs
│  └─ adr/                     # architecture decision records (D1..Dn)
├─ scripts/                    # dev/build/release helpers (no secrets)
├─ .github/ or .ci/            # build pipelines (installers, tests)
├─ .gitignore
├─ README.md
└─ LICENSE / COMMERCIAL        # commercial license terms
```

## 4.2 Rationale

| Decision | Why |
|---|---|
| Monorepo | One team, tightly-coupled contracts (OpenAPI → TS types), atomic cross-cutting changes, single CI to build the bundled installer. |
| `apps/` vs `services/` vs `packages/` | Clear separation of deployable clients, the backend service, and shared libraries. |
| Backend owns `stats/` once | Enforces the **single statistics engine** rule (§19) — no duplicate calc logic in UI or reports. |
| `db-schema/` holds ERD + reference data only | Schema/migrations authored in Phase 2; **no production or personal data** in the repo. |
| `docs/adr/` | Each approved `[DECISION Dn]` becomes an immutable ADR. |

## 4.3 Branch, commit & release conventions

- **Branches:** `main` (always releasable) + short-lived feature branches
  `feature/<phase>-<slug>`; one branch per roadmap work item.
- **Commits:** Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`), referencing
  the roadmap phase. Attribution lines per project policy.
- **Versioning:** SemVer for the app; phase tags (`phase-2-foundation`) for milestones.
- **Releases:** CI builds the signed Windows installer (Tauri bundler + PyInstaller
  sidecar), runs the full test suite, and publishes the auto-update artifact.

## 4.4 What `.gitignore` must exclude (integrity/security)

- Secrets of any kind: `.env`, credential files, provider tokens, DB passwords.
- Build artefacts: `target/`, `dist/`, `node_modules/`, `.venv/`, PyInstaller output.
- **Any real cricket data, media, or exported samples** (provenance/privacy) — samples
  for importer development live outside the repo or in an ignored `fixtures-private/`.
- Local config, logs, backups.

## 4.5 Documentation-as-code

`docs/` is version-controlled alongside code. Decisions, calculation methodologies and
the report catalogue are the contract the engine is tested against (deliverable 34), so
they stay in-repo and reviewed like code.
