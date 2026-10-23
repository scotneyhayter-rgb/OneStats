# OneStats — Phase 4 Implementation Plan

**Phase 4 — Organisations, Clubs, Associations & Competitions**
Status: **PLAN (awaiting approval)** · 2026-10-23 · Planning only, no implementation code.

Grounded in the Phase 1 specifications — deliverable **11** (cricket organisation data
model), **5** (ERD), **8/§8** (organisations), **16a** (real Cricket Statz structure) — and
built on the Phase 2/3 foundation (Tauri + FastAPI + PostgreSQL 17; workspace isolation with
**FORCE RLS** + transaction-scoped context; Argon2 auth + sessions; RBAC + audit; branding).

## Guiding principles (preserved from earlier phases)

- **Workspace isolation**: every new domain table carries `workspace_id` + **FORCE RLS**
  keyed on `onestats.workspace_id`; the runtime `onestats_app` role stays non-owner/DML-only;
  migrations run as `onestats_migrator` (migration history preserved, nothing reset).
- **Permissions + audit**: every mutation is permission-checked (deliverable 7) and written
  to the append-only `audit_log`.
- **Unknown ≠ zero**: historical facts are nullable with explicit "unknown"; never fabricate.
- **Provenance**: every importable entity keeps `source_system` + `source_ref` (idempotent
  re-import), honouring the Cricket Statz IDs (16a) **without adopting its UI**.
- **Historical correctness**: period-correct names/affiliations via time-bounded records;
  identities merged only under human control (mirroring the Phase 3 player-identity model).
- **Branding unaffected**: Phase 3 branding architecture is untouched.

> Phase 4 builds the **structural reference model** (who played whom, where, in what
> competition/grade/season). It does **not** build matches/scorecards (Phase 6) or the
> statistics engine (Phase 12).

---

## Stage 1 — Organisations & historical identity

**Objectives:** model clubs, associations, international teams and historical/defunct clubs;
their prior names; and controlled identity management (the same safe pattern as players).

**Deliverables:**
- `organisation` (`workspace_id`, `name`, `short_name`, `kind` = club|association|
  intl_team|historical_club, `is_historical`, `status`, `source_system`, `source_ref`).
- `organisation_name_history` (org, name, `valid_from`/`valid_to` nullable=open/unknown).
- `organisation_source_identity` (org ↔ CS `ClubID`, display name) — many per org.
- `organisation_merge` (reversible, audited) + `organisation_distinct_assertion`
  ("Definitely Different").
- Service + API: create/get/update/list, name-history, find-&-merge-duplicates, split/undo.

**Dependencies:** Phase 3 (workspaces, RBAC, audit). **DB migration:** `0005_organisations`.
**Security:** `workspace_id` + FORCE RLS; new permission `organisation.manage` (seeded;
granted to Super/Workspace Admin by default); merges need an explicit merge permission;
audited. **Tests:** live rolled-back — create/rename, cross-workspace isolation, merge/split,
name-only never auto-merges, source_ref idempotency, permission gating.
**Acceptance:** a workspace can hold clubs/associations/historical clubs with period-correct
names; two same-named clubs stay distinct unless merged with evidence; all audited; no
cross-workspace leakage.

---

## Stage 2 — Venues & Teams

**Objectives:** model grounds and the teams an organisation fields (per program), with their
own history and provenance.

**Deliverables:**
- `venue` (`workspace_id`, `name`, optional location/notes, `source_ref`; `"?"` → unknown).
- `team` (`workspace_id`, `organisation_id`, `program` = seniors|juniors|womens|girls|
  all_abilities|veterans|custom, `name`, `is_historical`, `source_ref`).
- `team_name_history`, `team_source_identity`, and team controlled-merge (same pattern).
- Service + API for venues and teams; link teams to their organisation.

**Dependencies:** Stage 1. **DB migration:** `0006_venues_teams`.
**Security:** workspace_id + FORCE RLS; **separate** permissions `venue.manage` (venues) and
`organisation.manage` (teams/orgs) per D34; audited. **Tests:** create/list, team→org link,
program classification, venue/team isolation + merge + provenance.
**Acceptance:** teams are attributable to an organisation and program; venues reusable;
same-named teams/venues distinct unless merged; period names resolvable.

---

## Stage 3 — Competitions, Divisions, Grades & Seasons

**Objectives:** model the competition structure teams play in, including the division/grade
distinction reconciled with Cricket Statz, and seasons over time.

**Deliverables:**
- `competition` (`workspace_id`, `name`, optional `association_id`→organisation, `source_ref`).
- `division` (competition, name) — optional grouping.
- `grade` (competition, name, junior/girls default **max 15 players**, `source_ref`).
- `season` (competition, label e.g. "2024/25", `start`/`end` nullable precision).
- `team_grade_entry` (team × grade × season) — which teams contested which grade when.
- Service + API; map Cricket Statz `divisions` → **grades** (16a). `[D32 provisional]` the
  **numeric enum codes, finals flags and match classifications are verified against source
  evidence**; any mapping that cannot be confirmed is left **unresolved, not guessed**.

**Dependencies:** Stages 1–2. **DB migration:** `0007_competitions`.
**Security:** workspace_id + FORCE RLS; permission `competition.manage`; audited.
**Tests:** competition→association link, grade defaults, season spans, team-grade entries,
isolation, provenance, the CS division→grade mapping.
**Acceptance:** a club's teams can be placed in a competition's grades per season; seasons
span 1919→present (no 150-year limit); CS grade names import cleanly; finals markers handled.

---

## Stage 4 — Playing conditions & season-specific rules

**Objectives:** capture rules by competition/season/grade (with later match-level override),
**unknown-aware**, and not hard-coded to "today".

**Deliverables:**
- `playing_condition` (scope = competition|season|grade, FKs, with resolution order
  match→grade→season→competition for later phases): structured core (`overs_limit`,
  `max_players`, `balls_per_over`, `innings_per_side`, `format`) **nullable = unknown**, plus
  `extra` JSONB for anything else.
- Resolution helper (effective conditions for a given competition/season/grade).
- Service + API to configure and read conditions; historical rule changes are versioned by
  season/grade, never applied retroactively across all seasons.

**Dependencies:** Stage 3. **DB migration:** `0008_playing_conditions`.
**Security:** workspace_id + FORCE RLS; `competition.manage`; audited.
**Tests:** resolution order, junior/girls max-15 default, **unknown stays unknown** (not
defaulted), era-specific rules don't leak across seasons, isolation.
**Acceptance:** rules configurable per competition/season/grade; unknown historical
conditions remain unknown; the audit engine (later) won't treat unknown as an error.

---

## Stage 5 — Organisation lifecycle: mergers, name changes & association transfers

**Objectives:** model how organisations evolve over time — renames, mergers/splits,
affiliations, and a club transferring between associations — as time-bounded relationships,
preserving history.

**Deliverables:**
- `organisation_relationship` (`from_org`, `to_org`, `type` = merger|rename|affiliation|
  association_transfer|predecessor, `valid_from`/`valid_to` nullable, `notes`, source).
- Execution flows that use Stage 1 merge where two records are truly one identity, vs. a
  *relationship* where two distinct orgs are linked (e.g., a club joining an association).
- Service + API; historical timeline view data.

**Dependencies:** Stages 1, 3. **DB migration:** `0009_org_relationships`.
**Security:** workspace_id + FORCE RLS; `organisation.manage` (+ merge permission for
merges); audited; reversible. **Tests:** rename vs merger vs transfer modelled distinctly;
time-bounded correctness; a match's org name resolves to its era; isolation; reversibility.
**Acceptance:** RMCC-style histories (predecessor clubs, association moves, renames) are
representable without overwriting history; period-correct resolution works.

---

## Stage 6 — Cricket Statz structural import (clubs/teams/venues/grades)

**Objectives:** populate the Phase 4 model from the real Cricket Statz export's reference
collections (clubs, teams, venues, divisions/grades), via staging → validation → identity
resolution → **administrator approval** → canonical, honouring source IDs — **without
adopting the Cricket Statz UI**.

**Deliverables:**
- Extend the Phase 1-designed Cricket Statz importer (deliverable 16/16a) with a **structural
  pass** mapping `clubs`→organisation, `teams`→team(+org), `venues`→venue,
  `divisions`→grade (+ finals markers), using `source_ref` for idempotent re-import and the
  Phase 3 identity-resolution rules (no name-only auto-merge).
- Import preview/diff, duplicate detection, conflict surfacing, approval, import history.

**Dependencies:** Stages 1–5; **and the Phase 1 open items** — confirmed Cricket Statz
**coded-enum legends** and **finals/grade mapping** (deliverable 16a.6/16a.7; §37.3). **DB
migration:** none new (reuses staging tables designed for Phase 8; a light `import_batch`
foundation may land here — see Decisions). **Security:** import runs to staging only;
promotion is permission-gated (`import.approve`) + audited; workspace-isolated; never
overwrites verified data. **Tests:** sample-driven (synthetic fixtures mirroring 16a), source_ref
idempotency, division→grade mapping, identity resolution, approval gating.
**Acceptance:** RMCC's clubs/teams/venues/grades load into the model, re-import is
idempotent, duplicates resolved under human control, provenance preserved.

> Note: Cricket Statz **match** import stays in Phase 8; Stage 6 imports only the
> **structural reference** data needed by Phase 4.

---

## Stage 7 — Desktop UI: Organisation & Competition management

**Objectives:** management screens in OneStats' own identity for organisations, teams,
venues, competitions/grades/seasons, playing conditions, the historical timeline, and the
find-&-merge tool — clear and simple for cricket administrators.

**Deliverables:** list/create/edit screens under **Settings → Organisation** (and within the
workspace), a historical-timeline view, a merge/relationship tool, all wired to the Stage
1–6 APIs; loading/empty/error states; responsive; permission-aware (hide what the user can't
do; server still enforces).

**Dependencies:** Stages 1–5 (6 optional). **DB migration:** none.
**Security:** respects auth/permissions/isolation; no privileged action without the server
check. **Tests:** frontend build + vitest for pure logic; **manual E2E** of create/edit/merge
flows (clearly distinguished from automated), with any test data cleaned up.
**Acceptance:** an admin can set up and maintain a club's organisations, teams, venues and
competition structure through the UI, in OneStats' identity (not a Cricket Statz clone).

---

## Cross-stage: security, migrations & testing standards

- **Migrations** `0005`–`0009` run as `onestats_migrator`; every workspace-scoped table gets
  RLS **+ FORCE** and a `workspace_isolation` policy; reference seeds (permissions) added
  before enabling RLS where needed (lesson from Phase 3).
- **Permissions** added this phase (D34, **separate**): `organisation.manage`,
  `competition.manage`, `venue.manage` — seeded (before enabling RLS) and mapped to roles
  (Super/Workspace Admin manage; read to members). Merges reuse the identity-merge permission.
- **Audit** on every create/update/merge/relationship/import-approval.
- **Isolation tests** (requirement, as in Phase 3) for each new workspace-scoped table.
- Backend: pytest (live rolled-back) + ruff; Frontend: tsc + vite + vitest; Native: cargo
  build; plus manual E2E for the UI stage.

## Dependencies & sequencing

```
Stage 1 ─┬─> Stage 2 ─┐
         │            ├─> Stage 3 ─> Stage 4
         └────────────┘        └─> Stage 5
Stages 1–5 ─> Stage 6 (needs CS enum/grade confirmations) ─> Stage 7 (UI)
```
External gate for **Stage 6**: the Phase 1 outstanding Cricket Statz confirmations
(enum legends, finals/grade mapping) — deliverable 37 §37.3.

## Approved decisions (D28–D36, recorded in deliverable 37 §37.1)

All **approved by the user (2026-10-23)**; D32 is **provisionally approved** pending source
verification.

- **D28 — APPROVED.** Preserve historical organisation/team identities; **admin-approved
  merge** of genuine duplicates, **audited and reversible/safely recoverable**; **never merge
  on names alone** (Phase 3 player-identity pattern).
- **D29 — APPROVED.** **Time-bound** organisation relationships + historical names;
  preserve **effective dates** and historical attribution.
- **D30 — APPROVED.** **Stable team identities** + season-specific competition entries.
- **D31 — APPROVED.** Competitions with **optional association ownership**.
- **D32 — PROVISIONALLY APPROVED.** Map Cricket Statz `divisions` → OneStats grades, but the
  **numeric enum codes, finals flags and match classifications must be verified against
  source evidence**; **unknown mappings remain unresolved, never guessed** (16a.6/16a.7).
- **D33 — APPROVED.** **Structured core + controlled JSONB extensions**; support historical
  rule changes incl. **balls-per-over, match formats, points, season-specific conditions**.
- **D34 — APPROVED.** **Separate** `organisation.manage`, `competition.manage` and
  `venue.manage` permissions, consistent with isolation/RBAC/audit.
- **D35 — APPROVED.** The Stage 1–7 sequence, with **Stage 6 gated on confirmed Cricket
  Statz enum + finals mappings**.
- **D36 — APPROVED.** **Minimal import-staging** where needed for Phase 4; **full Cricket
  Statz & third-party import deferred to Phase 8**.

## Additional requirements (per Phase 4 approval)

- Preserve all existing **Phase 2 & Phase 3** functionality; **never reset or overwrite
  existing database records**; migration history preserved (migrations `0005`+ only add).
- Maintain **OneStats' independent visual identity** (never a rebranded Cricket Statz).
- Ensure historical organisations, clubs, associations, grades and competition structures can
  be **researched accurately** (period-correct names, effective-dated relationships,
  unknown-aware).
- Provide a **stage-by-stage progress report after every completed stage**.
- At the **end of Phase 4**, provide the **complete 18-phase roadmap** and the **phase
  completion report**.

## Out of scope for Phase 4 (later phases)

Matches/scorecards (Phase 6), validation/verification engine (Phase 7), Cricket Statz
**match** import (Phase 8), discovery/research (9–10), media/OneVault (11), statistics engine
(12). Phase 4 delivers only the organisation/competition **structure** those phases rely on.
