# 37. Risk Register and Outstanding Decisions

**Deliverable 37 of 38** · §34

Consolidates the architectural decisions needing your approval and the project risk
register. Decisions are referenced inline across the docs as `[DECISION Dn]`.

## 37.1 Decisions requiring user approval

Priority: 🔴 blocks/shapes Phase 2 · 🟠 shapes a later phase · 🟡 refinement.

| ID | Decision | Options | Recommendation | Pri |
|---|---|---|---|:--:|
| **D1** | Backend topology | FastAPI sidecar service **/** logic-in-Rust/Tauri | **FastAPI sidecar** (stats/import/NLP ergonomics) | 🔴 |
| **D2** | Workspace isolation model | Single DB row-scoped + RLS **/** schema-per-ws **/** db-per-ws | **Single DB, row-scoped + RLS** (defence-in-depth) | 🔴 |
| **D7** | Backend packaging | PyInstaller sidecar **/** require Python **/** rewrite in Rust | **PyInstaller sidecar** (no user Python) | 🔴 |
| **D8** | Python dependency manager | uv **/** Poetry **/** pip-tools | **uv** (speed, lockfile) | 🟡 |
| **D18** | Client↔API transport security (LAN) | Internal CA/self-signed TLS **/** localhost-only (single PC) | **TLS via internal CA** for LAN; localhost for single-PC | 🔴 |
| **D3** | Junior/DOB default visibility | Hidden by default, grantable **/** visible to more roles | **RECOMMENDED FOR FINAL APPROVAL** — private by default; Wksp Admin + authorised People Mgr may access; Researcher/Reviewer granted separately when justified; never public/exported; age uses verified DOB only | 🟠 |
| **D4** | Captaincy Winning % min matches | 20 (proposed) **/** other | **20 eligible matches**, configurable | 🟠 |
| **D15** | Forfeit handling in captaincy/results | Count forfeit W/L **/** exclude | **Count defined-winner forfeits; exclude no-contest** (confirm vs RMCC rules) | 🟠 |
| **D10** | Abandoned/no-result in streaks & results | Skip (don't break) **/** break sequence **/** count | **Skip true no-results** (not W/L); break "known sequence" & flag | 🟠 |
| **D9** | "Consecutive matches" basis | Team-per-grade match sequence **/** all teams **/** calendar | **Team-per-grade chronological sequence** | 🟠 |
| **D11** | "Most 40s" band | 40–49 **/** 40+ | **RECOMMENDED FOR FINAL APPROVAL** — individual innings scores **40–49 inclusive**; 50+ excluded; separate from 50s/100s | 🟡 |
| ~~**D12**~~ | **Bowling-partnership definition — ✅ CONFIRMED AND RESOLVED 2026-10-21** | — | **Participation-based combination** — for any 2/3/4-player combination, Σ each member's bowler-credited wickets across the matches where **every** member played; players need **not** have bowled simultaneously or in the same innings; run-outs excluded; 0-wicket member still qualifies; missing figures ≠ confirmed zero. See deliverable 25 §25.3 | ✅ |
| **D13** | Catches: keeper split | Keeper catches counted in "Top Catches" **/** fielding-only | **RECOMMENDED — REQUIRES USER APPROVAL** — "Top Catches" = **fielding catches only** (exclude keeper); separate reports for fielding catches, keeper catches, keeper stumpings, total keeper dismissals, and optional combined (no double-count); unknown fielder/keeper never guessed | 🟡 |
| **D14** | Captain vs acting captain credit | Credit actual (acting) captain **/** nominal captain | **RECOMMENDED FOR FINAL APPROVAL** — credit the person who **actually captained** (acting captain when recorded as leading); retain both appointed+acting; never double-credit a match; unknown stays unknown; applies to all captaincy metrics | 🟠 |
| **D5** | Provider connectors in v1 | PlayHQ public only **/** add others | **PlayHQ public only**; defer the rest | 🟠 |
| **D6** | OneVault integration scope | Internal storage only for v1, adapter stubbed **/** build adapter now | **RECOMMENDED FOR FINAL APPROVAL** — OneStats runs fully independently on internal storage; OneVault optional via a storage-provider abstraction; future adapter only when a real supported interface exists; never modify OneVault; no hard dependency | 🟠 |
| **D16** | Ask OneStats NL approach | Rule/grammar (offline) **/** LLM intent→spec (validated) | **RECOMMENDED FOR FINAL APPROVAL** — deterministic NL→query first (numbers always from the engine, usable without any AI subscription); optional LLM-assisted interpretation later, approval + security gated; no private data to external AI without authorisation | 🟠 |
| **D17** | RMCC Lovable site integration | Read-only JSON feed **/** secure API **/** embeddable components **/** pre-rendered | **OPEN — REQUIRES WEBSITE INVESTIGATION** — design around a secure publishing interface + offline-capable public site; **recommend a read-only published JSON/snapshot feed**, but do **not** finalise until the real Lovable site is inspected | 🟠 |
| **D19** | Backup RPO / PITR | Daily `pg_dump` only **/** + WAL PITR | **Daily + optional WAL/PITR** for near-zero RPO | 🟡 |
| **D20** | **Historical web scraping as a CORE capability** (Phases 9–10) | Core scraping of publicly accessible sources **/** manual research only | **APPROVED BY USER** — core scraping of **publicly accessible** sources via per-source adapters + OCR, under strict guardrails (robots.txt, licensing, privacy, rate limits; never bypass access controls/paywalls; human review; confidence; no name-only merges). Deliverables 18 §18.2a, 19 | 🟠 |
| **D21** | **Historical Research Timeline** (season coverage) | Build coverage timeline **/** keep simple Research Gaps only | **APPROVED BY USER** — coverage classes (Comprehensive/Partial/Significant Gaps/**Unassessed**), transparent configurable methodology, completeness≠verification, confirmed-inactive≠missing-evidence, recalc after findings, audited. Deliverable 19 §19.6 | 🟠 |
| **D22** | **Mobile image/document uploads** (confirmed requirement) | — | **CONFIRMED REQUIREMENT** — QR-paired, time-limited secure sessions; camera/library/PDF; review queue; verification before official stats; privacy + audit; OneVault optional; LAN-first, remote later; dev server never public. Architecture [20a](20a-mobile-upload-architecture.md) **presented for review**. Core → Ph 11, mobile UI → Ph 16 | 🟠 |
| **D23** | **Desktop CSP / Tauri permissions** | Keep dev-default `null` **/** restrictive production CSP | **User: record `null` as dev-only limitation; plan restrictive production CSP + least-privilege Tauri capabilities** (deliverable 33 §33.5a) | 🟠 |
| **D2a** | **RLS enforcement model** | Plain RLS **/** FORCE + transaction-scoped context | **User-approved** — `FORCE ROW LEVEL SECURITY` on domain tables + **`SET LOCAL` transaction-scoped** workspace GUC; fail-closed. Phase 3 (deliverable 6 §6.7) | 🔴 (Ph 3) |
| **D24** | **Migration vs runtime DB role** | Single `onestats_app` owner+runtime **/** separate migrator(owner) + non-owner runtime | **User-approved to adopt** — `onestats_migrator`/owner runs DDL; runtime `onestats_app` is a **non-owner** with DML grants only (always RLS-bound, cannot alter/disable policies). Needs superuser to create the role. Phase 3 (deliverable 6 §6.7) | 🔴 (Ph 3) |
| **D-toolchain** | Frontend toolchain | React 19 / Vite 8 / Tailwind 4 / TS 6 | **ACCEPTED PROVISIONALLY by user** — subject to compatibility checks + passing tests (currently all green) | 🟡 |

## 37.2 Risk register

Likelihood (L) / Impact (I): H/M/L.

| ID | Risk | L | I | Mitigation | Owner/phase |
|---|---|:--:|:--:|---|---|
| R1 | **External provider APIs gated/limited** (PlayHQ docs auth-walled; others no data API) | H | H | Design modular connectors; verify PlayHQ key + scorecard depth early; others = manual/negotiated; mark unverified | Ph 8 |
| R2 | **Cricket Statz formats undocumented** — JSON **now sampled** (deliverable 16a); MXP/CSV specs still unknown | M | M | JSON importer built on the real sample; MXP/CSV only when samples supplied; staging + validation | Ph 8 |
| R2b | **Cricket Statz coded-enum legends partly unknown** — 6 Howout codes + Result 1 + matchtype 1 now confirmed; Result 2/3/4/8/9, Howout 5/7/8/9/10 & rare, iresult, Batting/Bowlingtype still unconfirmed (16a.6) | M | H | Do **not** hard-code guessed legends; preserve original codes; confirm before promotion; unresolved codes = "out of unknown manner", flagged | Ph 8 |
| R2c | **Cricket Statz JSON export is LOSSY** — authoritative Final/Grand-final flags, winning margin, sub-result, D/L, **"exclude from stats"**, Captain2, and several innings fields are **absent from the export** (16a.9/16a.10) | H | H | Treat classification as provisional (never infer from round alone); model `include_in_statistics` separately; re-capture lost fields in verification, or obtain a richer export/DB; flag all affected matches | Ph 8 |
| R3 | **Web scraping legal/ToS/privacy risk** (copyright, access controls, personal data) | M | H | **Publicly accessible sources only**; per-adapter access terms; honour robots.txt/licensing/privacy/rate limits; **never bypass** paywalls/auth; legal review per source; approval-gated; provenance kept (deliverable 18 §18.4) | Ph 9 |
| R16 | **OCR / extraction inaccuracy** (unclear scans, bad parses) | H | M | Per-field confidence; **preserve uncertainty** (show OCR text + source image); low-confidence never auto-promoted; human review (deliverables 18, 19) | Ph 9–10 |
| R17 | **Coverage metric misread** (a % mistaken for verified completeness) | M | M | **Unassessed** instead of a fabricated %; completeness≠verification shown distinctly; transparent, documented, configurable methodology; audited (deliverable 19 §19.6) | Ph 10 |
| R18 | **Scraper fragility** (source HTML/layout changes) | M | L | Modular adapters, tolerant parsing, monitoring; a broken adapter degrades to manual research, not bad data | Ph 9 |
| R19 | **Mobile upload abuse** (malware, oversized/wrong-type files, exposure) | M | H | Content-based type verification + allowlist; size limits; malware-scan hook + quarantine; safe non-guessable storage paths; **dev server never public**; LAN binding session-gated only (deliverable 20a §20a.7) | Ph 11/16 |
| R20 | **Upload pairing/session compromise** (token theft/replay) | L | H | Short-TTL scoped single-use tokens in the QR (not real credentials); revocable + audited; TLS on LAN; no long-lived secret on the phone (20a §20a.3) | Ph 11/16 |
| R21 | **HEIC / extracted-stat quality** (format handling, bad OCR) | M | M | Preserve HEIC original + web-safe preview; extracted stats are advisory and **require human verification** before official records (20a §20a.4) | Ph 11 |
| R4 | **Statistical correctness** (ambiguous counting, unknown handling) | M | H | Fix definitions now (D4,D9–D15); golden-fixture tests; known-minimum semantics; release gate | Ph 12–13 |
| R5 | **Workspace isolation leak** | L | H | 3-layer enforcement (authz + scoping + RLS); isolation tests; no-unscoped-query CI gate | Ph 3 |
| R6 | **Scorecard grid UX** (fast entry is hard) | M | M | Prototype early (Ph 6); keyboard/autosave; evaluate grid lib | Ph 6 |
| R7 | **Sidecar packaging/startup** (frozen Python) | M | M | PyInstaller spike in Ph 2; warm start; splash | Ph 2 |
| R8 | **RMCC website integration unknown** | M | M | Confirm capability in Ph 15; preserve design; data+branding only | Ph 15 |
| R9 | **OneVault API unknown** | M | L | Keep OneVault optional; capability-detect; internal storage default | Ph 11 |
| R10 | **Privacy breach of junior/DOB data** | L | H | Hidden by default; exclude from public/portal; never age-rank on uncertain DOB | Ph 5,16 |
| R11 | **Secret leakage** (DB password/tokens) | L | H | Credential Manager only; never in code/logs/backups; superuser never used by app | All |
| R12 | **Data loss** | L | H | Automated backups + tested restores; pre-migration backups; offsite encrypted copy | Ph 2+ |
| R13 | **Scope creep across 18 phases** | M | M | Phase gates; approval between phases; this doc set as the baseline | All |
| R14 | **Win10 EOL / platform drift** | M | L | Add Win11 to test targets; document min OS/WebView2 | Ph 2,17 |
| R15 | **Performance of large historical datasets** | M | M | Indexing + materialised views measured before optimising | Ph 12 |

## 37.3 Outstanding questions for the user

**A. Cricket Statz import (unblocks Phase 8 promotion — the data is in hand):**
1. **Remaining coded-enum legends.** Confirmed via screenshots: `Result 1`=Home Win;
   `matchtype 1`=1 innings/side; `Howout` 0=dnb,1=not out,2=bowled,3=caught,4=C&B,6=LBW.
   Still needed: `Result` 2/3/4/8/9; `matchtype` 2/3; `Howout` 5,7,8,9,10 (confirm
   ct-behind/run-out/stumped/retired/unknown) and the **rare** codes 20/22/23/24; plus
   **CaughtFld, Retired, UnknownOut** semantics; `iresult`; `Battingtype`; `Bowlingtype`.
2. **Finals/grand-final mapping.** The Cricket Statz UI has explicit **Final / Grand-final
   flags** that are **NOT in the JSON export** — only `round`/`Grade`. Confirm the mapping,
   and whether a **richer export or direct Cricket Statz DB access** is available that
   preserves the flags (and margin, sub-result, D/L, "exclude from stats", Captain2).
3. **Captain2 / Keeper2 meaning.** Keeper2 is in the JSON; Captain2 is not. What do they
   represent (joint/deputy captain; substitute keeper)? No captaincy credit to Captain2
   until confirmed.
4. **Lost authoritative fields.** Accept per-match **re-capture** of Final/GF, winning
   margin, sub-result, D/L and the **statistical-inclusion ("exclude from stats")** state,
   or supply a richer source? (deliverable 16 §16.9)

**B. RMCC competition rules (needed before Phase 12–13 counting):**
3. **Finals vs Grand Finals** definition for RMCC.
4. **Forfeit** treatment (D15) for each area in deliverable 24 §24.2a (appearances, wins,
   captaincy, winning %, streaks, player records).
5. **Streak** rules (D10): how abandoned, no-result and missing historical fixtures are
   treated; what counts as a "match" for consecutive-match reports (D9).
6. Competition rules that changed over time (so era-specific rules are recorded, not
   back-applied).

**C. Decisions to approve:**
7. D3 (junior/DOB privacy), D6 (OneVault scope), D11 (Most 40s = 40–49), D13 (catches
   split), D14 (captaincy attribution), D16 (Ask OneStats deterministic-first) — all
   *recommended for final approval*. **D12 is CONFIRMED & RESOLVED** (deliverable 25
   §25.3). D4 (20-match captaincy threshold) to confirm.

**D. External/integration:**
8. Arrange **PlayHQ API access** for RMCC (and confirm cricket scorecard field access).
9. **D17** — provide access to inspect the RMCC Lovable website so a publishing method can
   be chosen (recommend a read-only published feed; not finalised until inspected).
