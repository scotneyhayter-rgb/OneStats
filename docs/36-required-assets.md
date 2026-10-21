# 36. Required Software and Development Assets

**Deliverable 36 of 38** · §3

What is already available (audited 2026-10-21) and what must be added for Phase 2+.

## 36.1 Already provisioned ✅ (no action)

Windows 10 Pro 22H2 · VS Code 1.141.2 · Git 2.45.2 · Node 24.20.0 LTS (npm 11.19.0) ·
Python 3.12.10 · Rust/Cargo 1.99.1 (MSVC) · MSVC C++ Build Tools (VS 2022, cl.exe 14.44) ·
Edge WebView2 155 · PostgreSQL 17.11 (`postgresql-x64-17`) · Claude Code.
PostgreSQL roles: `postgres`, `scotney` (superusers), `onestats_app` (app role, owns
`onestats`).

## 36.2 To add in Phase 2 (tooling)

| Asset | Purpose | Notes |
|---|---|---|
| **pnpm** | Frontend package manager | `corepack enable` or install |
| **Tauri CLI** (+ crates) | Desktop build | `cargo install tauri-cli` / npm |
| **uv** (or Poetry) | Python env/deps | `[DECISION D8]` — recommend uv |
| **FastAPI, Pydantic v2, SQLAlchemy 2, Alembic** | Backend | pip/uv |
| **PyInstaller** | Freeze the FastAPI sidecar | `[DECISION D7]` |
| **pytest** (+ factory/fixtures), **Vitest**, **Playwright** | Testing | deliverable 34 |
| **openpyxl**; **WeasyPrint** or **ReportLab** | Excel/PDF export | pick in Phase 12 |
| **keyring** (or Tauri plugin) | Windows Credential Manager | secrets (deliverable 33) |
| **APScheduler** (or DB-backed queue) | Background jobs + scheduled research tasks | no external broker |
| **pgTAP** (optional) | RLS/policy tests | deliverable 34 |
| **httpx / requests** | Polite HTTP fetching (timeouts, backoff, caching) | scraping (Phase 9) |
| **BeautifulSoup4 + lxml** | HTML parsing/extraction | scraping |
| **Playwright (Python)** | JS-rendered pages only when needed | scraping; heavier — use sparingly |
| **pandas** | Tabular extraction/normalisation of scraped data | scraping/import |
| **pdfplumber / pdfminer.six** | PDF text/table extraction | digitised docs |
| **Tesseract + pytesseract** (or equivalent OCR) | Newspaper-image OCR with per-field confidence | scraping (Phase 9/10) |
| **rapidfuzz** | Fuzzy name/alias/duplicate matching (suggestions only) | identity, discovery |

## 36.3 Credentials & access (user-provided)

| Item | Needed for | When |
|---|---|---|
| `onestats_app` password in Windows Credential Manager | App DB access | Phase 2 start |
| TLS cert / internal CA for LAN | Client↔API security (`[DECISION D18]`) | Phase 2 |
| Code-signing certificate | Signed installer + auto-update | Phase 2 (before release ideally) |
| **PlayHQ API key** (RMCC) | Match import connector | Phase 8 (request early) |
| ✅ **Cricket Statz JSON export** | **ACQUIRED** — real RMCC sample inspected (deliverable 16a); JSON importer is now the core path | Done |
| **Cricket Statz coded-enum legends** (Result, matchtype, Howout, iresult, Battingtype, Bowlingtype) + finals/grand-final classification rules | Correct JSON import (not in the file, deliverable 16a.6/16a.7) | **Before Phase 8 promotion** |
| Cricket Statz MXP/CSV/Excel samples (if those formats are also needed) | Those importers (schemas unverified) | Phase 8 (only if required) |
| RMCC Lovable website integration details | Publishing (`[DECISION D17]`) | Phase 15 |
| (Optional) LLM access for Ask OneStats | NL intent mapping (`[DECISION D16]`) | Phase 14 |
| (Optional) OneVault API details | Media integration (`[DECISION D6]`) | Phase 11 |

## 36.4 Design/brand assets

RMCC logo(s) and official colours (deliverable 9) for branding; sample report layouts if
the club has a preferred style.

## 36.5 Infrastructure (future / optional)

Offsite/secondary encrypted backup location (deliverable 32); optional dedicated server or
cloud host for a later phase (§30). None required for the RMCC single-PC/LAN start.
