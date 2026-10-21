# 1. Executive Project Overview

**Deliverable 1 of 38** · OneStats Phase 1

## What OneStats is

OneStats is a professional, commercial **cricket statistics, historical-research and
records-management desktop application** for cricket clubs, associations and
international-cricket research. It is the second app in the **One** software family
(sibling to OneVault, a privacy-first media cataloguer — a *separate* project that
OneStats never modifies). Tagline: *Cricket Statistics Made Simple* — Lovable-grade
ease of use with the depth of a serious statistics system.

The first production workspace is the **Rhymney/Moyston Cricket Club (RMCC)**, an
Australian club whose current scoring platform is **PlayHQ**. A second workspace,
**International Cricket**, follows. Each workspace is fully isolated.

## What Phase 1 delivers

Phase 1 is **planning and architecture only**. This deliverable set (38 documents)
defines *what* OneStats will be and *how* it will be built, without building it:

- A recommended **technical architecture** and **technology-stack assessment**
  (Tauri + React + TypeScript backed by a Python/FastAPI service and PostgreSQL 17).
- A complete **PostgreSQL entity-relationship design** honouring the hard integrity
  rules (unknown ≠ zero, provenance preserved, workspace isolation, least privilege).
- The full **RMCC report catalogue** with *exact* counting methodologies for every
  record, including the contested ones (bowling partnerships, captaincy %).
- The **18-phase roadmap** with dependencies and risks, and a **detailed Phase 2
  implementation plan**.
- A **feasibility matrix** for third-party providers and Cricket Statz formats, built
  from real investigation and honestly caveated where providers gate their docs.
- A **risk register**, a list of **architectural decisions requiring your approval**,
  and a **Phase 1 acceptance checklist**.

## Current state (environment audit — §34 first actions)

| Check | Finding |
|---|---|
| Existing OneStats code | **None.** `C:\OneProjects\OneStats` contains only the master prompt + empty `docs/`. Greenfield. |
| Completed work | None prior to this Phase 1 documentation. |
| Cricket Statz data | **Real RMCC JSON export inspected** (940 matches, 3,595 players, 1919–2026, clean internal refs) — see [16a-cricket-statz-json-analysis.md](16a-cricket-statz-json-analysis.md). JSON import is now the core migration path. |
| Dev environment | Ready: VS Code 1.141.2, Node 24.20.0 LTS, Python 3.12.10, Rust 1.99.1 (MSVC), MSVC C++ Build Tools, WebView2 155, PostgreSQL 17.11, Git 2.45.2. |
| PostgreSQL roles | `postgres`/`scotney` (superusers, admin only), `onestats_app` (non-superuser LOGIN, owns db `onestats`). App will use `onestats_app` only. |
| Missing dependencies | No blockers for Phase 2 start. Minor tooling to add in Phase 2 (pnpm, uv/poetry, pgTAP optional) — see deliverable 36. |

Full environment detail: [03-technology-stack-assessment.md](03-technology-stack-assessment.md).

## Recommended architecture (one-paragraph form)

A **single-user-facing desktop app** (Tauri shell, React/TypeScript/Tailwind/shadcn UI)
talks over local HTTP/IPC to a **local Python/FastAPI service** that owns all business
logic and the **one deterministic statistics engine**. FastAPI connects to
**PostgreSQL 17** as the least-privilege `onestats_app` role. A central "server" PC runs
PostgreSQL + the FastAPI service; other desktop clients on the LAN connect to it.
Website publishing and the mobile portal are fed by a **separate read-only publication
cache** so the public site stays up even when the OneStats server is offline. Media
lives in internal storage by default, with optional OneVault integration and external
references. See [02-technical-architecture.md](02-technical-architecture.md).

## Key technical decisions requiring approval

These are the decisions that most shape Phase 2; the full list with options and
recommendations is in [37-risk-register-and-decisions.md](37-risk-register-and-decisions.md).

1. **Backend topology** — adopt the local FastAPI sidecar service (recommended) vs.
   pushing logic into Tauri/Rust. *Recommended: FastAPI sidecar.*
2. **Workspace isolation mechanism** — single database with a mandatory
   `workspace_id` on every row + enforced query scoping, vs. schema-per-workspace vs.
   database-per-workspace. *Recommended: single DB, row-scoped, defence-in-depth.*
3. **Captaincy winning-% denominator** and the **20-match** qualification threshold.
4. **Bowling-partnership counting methodology** — ✅ **RESOLVED** (confirmed
   participation-based combination method, deliverable 25 §25.3).
5. **Provider connector scope for v1** — PlayHQ public connector only, others deferred.
6. **Media storage default** and OneVault contract assumptions.

## Outstanding questions for the user

- Confirm the RMCC competition rules that affect counting (finals vs grand finals
  definition, forfeit handling, what counts as a "match" for streaks) — see the
  remaining-questions list in [37-risk-register-and-decisions.md](37-risk-register-and-decisions.md) §37.3.
- Provide the **Cricket Statz coded-enum legends** (Result, Howout, matchtype, iresult,
  Battingtype, Bowlingtype) and the finals/grand-final classification rules — the real
  JSON is in hand but these legends are not in the file (deliverable 16a.6–16a.7).
- Approve the recommended decisions D3, D6, D11, D13, D14, D16 (D17 awaits website
  investigation; D12 is confirmed).
- Arrange **PlayHQ API access** for RMCC; confirm whether the RMCC Lovable website can
  expose/consume a publishing feed.

## What happens next

On approval, Phase 2 (Windows Desktop & Server Foundation) begins per
[35-phase-2-implementation-plan.md](35-phase-2-implementation-plan.md). Nothing is
built until you approve.

> See the end-of-phase report in the session summary for the full acceptance wording.
