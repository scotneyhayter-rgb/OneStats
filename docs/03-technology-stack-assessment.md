# 3. Technology Stack Assessment

**Deliverable 3 of 38**

Evaluation of the proposed stack (§2) against OneStats' needs, with the provisioned
environment (§3) and compatibility concerns. Verdict column: ✅ adopt · ⚠️ adopt with
caveat · ❓ needs decision.

## 3.1 Provisioned environment (audited 2026-10-21)

| Tool | Version | Verdict | Notes |
|---|---|---|---|
| OS | Windows 10 Pro 22H2 (19045), 32 GB RAM, ~418 GB free | ✅ | Ample for dev + local PG. Win10 EOL (Oct 2025 mainstream) — plan Win11 test target. |
| VS Code | 1.141.2 (on PATH) | ✅ | — |
| Git | 2.45.2 | ✅ | Repo not yet initialised (see deliverable 4). |
| Node.js | 24.20.0 LTS, npm 11.19.0 | ✅ | Use for the React/Tauri frontend. |
| Python | 3.12.10 (`python`), 3.14.7 (`py`) | ✅ | **Pin 3.12** for the backend (ecosystem maturity). |
| Rust / Cargo | 1.99.1 (MSVC host) | ✅ | For Tauri builds. |
| MSVC C++ Build Tools | VS 2022, cl.exe 14.44 | ✅ | Needed by Tauri/native crates. |
| Edge WebView2 | 155.0.4283.62 | ✅ | Tauri runtime present. |
| PostgreSQL | 17.11 (`postgresql-x64-17`, localhost:5432) | ✅ | Roles ready; app uses `onestats_app`. |

**No missing blockers for Phase 2.** Tooling to add in Phase 2 is listed in
[36-required-assets.md](36-required-assets.md).

## 3.2 Layer-by-layer assessment

### Desktop shell — Tauri 2 (Rust) ✅
- **Pros:** tiny installer vs Electron, lower memory, native Windows integration,
  built-in auto-updater, secure IPC, OS keychain access, first-class sidecar support for
  bundling the Python backend. WebView2 already present.
- **Cons/caveats:** Rust build toolchain required (present); WebView2 version drift
  across client PCs — pin a minimum and let the Evergreen runtime update. Multi-window
  data grids need care for performance.
- **Verdict:** Adopt. Best fit for a secure, lightweight Windows desktop app.

### UI — React + TypeScript + Tailwind + shadcn/ui ✅
- **Pros:** mature, accessible component primitives (shadcn/Radix), excellent for
  data-dense screens and the spreadsheet-style scorecard grid, consistent theming for
  per-workspace branding (CSS variables), strong typing end-to-end with the API.
- **Caveats:** the **fast scorecard grid** (keyboard nav, autosave, validation) is the
  single hardest UI piece — prototype early; consider a dedicated grid library
  (e.g. TanStack Table + custom cell editing) `[CANDIDATE]`.
- **Verdict:** Adopt.

### Backend — Python 3.12 + FastAPI ⚠️
- **Pros:** ideal for the deterministic stats engine, importers/connectors, audit rules
  and Ask OneStats NLP; async; Pydantic v2 typing; testable; fast iteration with Claude
  Code.
- **Caveats:** must be **packaged** so end users need no Python (PyInstaller sidecar,
  `[DECISION D7]`); startup time of a frozen Python binary; keep it a single service, not
  a sprawl.
- **Verdict:** Adopt as a bundled local service/sidecar. The main architectural
  `[DECISION D1]`: FastAPI service vs. logic-in-Rust. Recommendation: **FastAPI**.

### Database — PostgreSQL 17 ✅
- **Pros:** already provisioned; rich constraints and CHECKs enforce integrity rules at
  the storage layer; **Row-Level Security** supports workspace isolation defence-in-depth;
  JSONB ideal for flexible provenance/source metadata and playing conditions; window
  functions and CTEs make the statistics engine tractable in SQL; `pg_dump`/PITR for
  backups.
- **Caveats:** keep heavy stats either in well-indexed queries or materialised views
  refreshed on verification — measure before optimising.
- **Verdict:** Adopt.

### Supporting choices

| Concern | Recommendation | Verdict |
|---|---|---|
| ORM + migrations | SQLAlchemy 2.x + Alembic | ✅ (migrations are Phase 2+) |
| API schema/validation | Pydantic v2 | ✅ |
| Package mgmt (frontend) | pnpm | ⚠️ add in Phase 2 |
| Package mgmt (backend) | uv (fast) or Poetry | ❓ `[DECISION D8]` — recommend **uv** |
| Background jobs | APScheduler or DB-backed queue in-process | ✅ (no external broker) |
| PDF export | WeasyPrint or ReportLab (server-side, branded) | ⚠️ pick in Phase 12 |
| Excel export | openpyxl | ✅ |
| Credential storage | Windows Credential Manager via `keyring`/Tauri | ✅ |
| Testing | pytest (+ pgTAP optional), Vitest + Playwright | ✅ (deliverable 34) |
| Ask OneStats NLP | intent → deterministic query mapping (no LLM invents numbers) | ✅ (deliverable 28) |

## 3.3 Compatibility concerns & mitigations

| Concern | Impact | Mitigation |
|---|---|---|
| Frozen Python sidecar size/startup | UX | PyInstaller one-dir, warm start, splash in Tauri |
| WebView2 version drift across clients | Rendering bugs | Pin min version; Evergreen auto-update; test matrix |
| Win10 end-of-life | Support window | Add Win11 to test targets; document min OS |
| Rust/MSVC toolchain on build machine only | Dev onboarding | Document setup; CI builds installers |
| PostgreSQL major upgrades | Data migration | Alembic + documented `pg_dump` upgrade path |
| LAN latency for multi-client grid | Entry UX | Optimistic UI + autosave; keep payloads small |

## 3.4 Alternatives considered (and rejected for now)

- **Electron** instead of Tauri — larger footprint, weaker native security story.
- **Node/TypeScript backend** instead of Python — loses the statistics/NLP ergonomics;
  would duplicate logic. Rejected.
- **SQLite** instead of PostgreSQL — simpler single-user, but PG is provisioned, scales to
  the LAN/server model, and gives RLS + stronger concurrency. Adopt PG.
- **Rust-only (no Python)** — viable but slower to build the stats/import/NLP surface
  with a small team; revisit only if sidecar packaging proves painful.

**Overall verdict: the proposed stack is sound and recommended, with the FastAPI
sidecar packaging and the backend-topology decision (D1) being the items to confirm.**
