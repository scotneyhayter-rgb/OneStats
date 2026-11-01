# OneStats — Bug Register

Comprehensive pre-acceptance audit (Phases 1–13). Opened 2026-10-26.
Each entry records severity, module, reproduction, root cause, the fix, the tests added, the
verification result and the commit. Defects found during the audit are fixed within the authorised
architecture (one engine, no historical-data changes, no weakened validation).

Severity key: **CRITICAL** (data corruption / security / workspace leakage / major failure) ·
**HIGH** (wrong statistics, broken core workflow, missing agreed functionality) ·
**MEDIUM** (functional/consistency/performance/usability) · **LOW** (cosmetic / minor UX).

---

## BUG-001 — Competing career-statistics path with a hard-coded six-ball-over economy
- **Severity:** MEDIUM (statistics accuracy + architecture: competing calculation)
- **Module:** Statistics Engine; API `GET /stats/people/{id}`
- **Description:** `recalc.official_player_batting` / `official_player_bowling` re-implemented career
  aggregation with their own SQL, parallel to the Phase 12 engine (`engine.person_batting` /
  `person_bowling`). The bowling variant computed economy as `runs * 6 / balls`, assuming six-ball
  overs — incorrect for the eight-ball-over eras that are standard in historical Australian club
  cricket (pre-1979). Two code paths for the same figure is a competing calculation.
- **Steps to reproduce:** Call `GET /workspaces/{w}/stats/people/{id}` for a bowler whose matches used
  eight-ball overs → the returned `economy` is computed on six-ball overs (overstated).
- **Expected:** One authoritative engine; economy honours the configured over length.
- **Actual:** A second aggregation path; economy fixed to six balls.
- **Root cause:** Phase 7 legacy helpers left wired to an endpoint after the Phase 12 engine superseded
  them.
- **Fix:** `official_player_batting`/`official_player_bowling` now delegate to the one engine
  (merge-aware, over-length-parameterised). The unused `_merge_aware` helper was removed; `not_out` is
  kept as a back-compat alias of the engine's `not_outs`.
- **User-visibility:** None in the desktop app — the client wrapper `officialPersonStats` is not called
  by any screen; the Player Profile uses the engine. The endpoint is nonetheless corrected.
- **Tests added/affected:** `tests/test_audit_stats_reference.py::test_bowling_reference_with_eight_ball_overs`
  proves economy changes with over length; `test_recalc.py` and `test_import_integrity.py` continue to pass.
- **Verification:** PASSED. **Commit:** see audit commit.

## BUG-002 — `person_captaincy` always returned zero (captaincy silently blank)
- **Severity:** MEDIUM (wrong statistics on the Player Profile)
- **Module:** Statistics Engine; Player Profile (Captaincy)
- **Description:** `engine._person_agg` returned an empty default dict whenever its SELECT lacked a
  `matches` column. The captaincy SELECT has no such column, so every per-person captaincy aggregate
  returned zeros — the profile's Captaincy figures/tab were silently blank.
- **Steps to reproduce:** Open a known captain's profile → Captaincy shows 0s despite captaincy history.
- **Root cause:** The empty-result guard keyed on a column not present in all calculators.
- **Fix:** The guard now trips only on a genuinely empty result (`r is None`); the aggregate always
  returns one coalesced row otherwise.
- **Tests added/affected:** `test_audit_stats_reference.py::test_captaincy_win_pct_reference`;
  the Player Profile render test.
- **Verification:** PASSED. **Commit:** a4190c6 (immediately before the audit; re-confirmed during it).

## BUG-003 — Player-profile PDF forced into landscape
- **Severity:** MEDIUM (professional presentation)
- **Module:** Reporting / PDF export
- **Description:** `build_pdf` selects landscape when any section exceeds six columns. The profile's
  eight-column season table forced the whole document — cover and narrow discipline tables included —
  into landscape, giving a sparse cover and poorly-proportioned pages.
- **Steps to reproduce:** Export a player profile PDF → cover and summary render landscape.
- **Fix:** `player_pdf` now declares `orientation="portrait"`; the season table fits A4 portrait.
- **Verification:** Rendered to image (pymupdf) before/after — now portrait, two pages, professional
  cover + career summary + season + records + milestones + awards. **Commit:** see audit commit.

## BUG-004 — PDF cover / section-heading duplication
- **Severity:** LOW (cosmetic)
- **Module:** Reporting / PDF export
- **Description:** (a) The player-profile cover printed the club name twice (`subtitle` equalled
  `workspace_name`, which the running header already shows). (b) Single-section reports (e.g. Batting —
  Leading Run Scorers) printed the document title again as the first section heading.
- **Fix:** `player_pdf` sets `subtitle=None`; `build_pdf` skips a section heading identical to the
  document title.
- **Verification:** Rendered to image — club name appears once; the batting report shows its title once
  (and fits one extra row per page). **Commit:** see audit commit.

## BUG-005 — `onboarding_draft` has no row-level security (by design; not a tenant leak)
- **Severity:** LOW (defense-in-depth / consistency) — **not** a confirmed vulnerability
- **Module:** Database; Workspaces; Onboarding
- **Description:** An RLS coverage probe found `onboarding_draft` is the only table with a
  `workspace_id` column that has neither RLS, FORCE, nor an isolation policy (all 60+ other
  workspace-scoped tables have all three).
- **Assessment:** Intentional. `onboarding_draft` is global, pre-workspace wizard state owned by
  platform Super Admins; its `workspace_id` is a nullable reference to the workspace being created, not
  a tenant partition key. Every onboarding endpoint requires `require_super_admin`; draft IDs are random
  UUIDs; the row holds no tenant cricket or member data. No cross-tenant data path exists.
- **Recommendation (not implemented, to avoid destabilising onboarding):** scope
  `get_draft`/`save_draft`/`activate_draft` by `created_by` so one Super Admin cannot read or modify
  another's in-progress draft (defense-in-depth among co-trusted platform operators).
- **Verification:** `rls_audit.py` (every other workspace table is FORCE RLS + policy) + endpoint
  review. **Status:** Documented risk; see `ONESTATS_REMAINING_RISKS.md`.

## BUG-006 — PDF/CSV exports did not open (popup-blocked) — found in acceptance 2026-10-26

- **Symptom:** The player-profile PDF (and other exports) "does not open" when the button is clicked.
- **Cause:** The export fetches the file (auth header) and makes a blob URL, then called
  `window.open(blobURL, "_blank")` **after the `await`** — outside the click gesture — so the browser's
  popup blocker silently stopped it. The request itself returned **200 OK** (valid PDF).
- **Fix:** Added `openBlobUrl()` (lib/utils) — a programmatic anchor with `download`, which is not
  popup-blocked and works in the browser and the Tauri webview. Applied to the profile PDF, Club Record
  Book PDF, report PDF/CSV export and the catalogue index PDF. (Publishing already used an anchor.)
- **Verification:** typecheck clean; retest in the app (exports now download/open). **Status:** FIXED,
  awaiting user retest.

---

## BUG-007 — Recalc assumed a six-ball over when the over length was unrecorded

- **Severity:** MEDIUM (statistics accuracy — fielding/economy honesty)
- **Module:** `onestats/domain/recalc.py` (`recompute_player_bowling` contribution build)
- **Description:** When a match had **no recorded `balls_per_over`**, the per-match bowling
  contribution still converted balls→overs by dividing by a hardcoded `6` and then set
  `overs_known = 1`. This contradicts the stated rule (and the engine's design): an unrecorded over
  length must leave that match's overs **unknown**, so it is excluded from career economy and the
  figure is flagged — never silently computed as if the match were six-ball cricket.
- **Steps to reproduce:** Recalc a bowler who has one match in a competition with
  `balls_per_over = 6` set and one match with no over length recorded → the career economy folded the
  unrecorded match in as six-ball overs and `economy_incomplete` was `False` (claimed complete).
- **Expected:** Only matches with a recorded over length contribute to true-overs economy;
  `economy_incomplete` is `True` when any contributing match's over length is unrecorded. Where a
  bowler's matches are *all* unrecorded, the leaderboard/profile still shows a figure via the
  requested `over_length` fallback (default 6) — now correctly flagged as assumed.
- **Root cause:** The `legal_balls` conversion path fell back to `/6` and `overs_known` was derived
  from `overs > 0` rather than from whether the over length was actually recorded. (The `overs_text`
  path, where overs are recorded directly, is correctly over-length-independent and is unchanged.)
- **Fix:** In the balls→overs path, only accumulate overs when `balls_per_over` is known; otherwise
  mark the match's over length unknown (`overs_len_known = False`). `overs_known` is now
  `1` only when the over length was recorded **and** overs were accrued. No number changes for the
  common modern (six-ball) case computed via the `over_length=6` fallback; mixed-era and unrecorded
  matches are now handled honestly.
- **User-visibility:** Stored contributions are unchanged until a match is recalculated. For a
  workspace whose competitions/seasons do **not** set `balls_per_over`, a recalc will flag economy as
  assumed (figure unchanged) rather than claiming it complete; setting `balls_per_over` on the
  competition/season (e.g. 6 for modern grades) records the true length and clears the flag.
- **Tests:** `tests/test_integrity_economy_keepers.py::test_economy_flagged_when_over_length_unrecorded`
  and `tests/test_audit_stats_reference.py::test_bowling_reference_with_eight_ball_overs` now pass;
  `test_career_economy_across_mixed_over_lengths` and `test_stats_engine.py::test_bowling_engine`
  continue to pass.
- **Verification:** PASSED (both target files green; full suite re-run). **Status:** FIXED.

---

## Observations (not defects — logged for a future phase)

- **OBS-1 (PARTIAL feature):** "Best Bowling in a Match" ranks by wicket count only; it does not carry
  the runs conceded, so it neither tie-breaks on runs nor shows a "7/23"-style figure. The per-innings
  best (BBI wickets + runs) is already stored in the ledger, so surfacing full figures is a contained
  enhancement.
- **OBS-2:** Shared run-outs — the scorecard model records a single `fielder_person_id` per dismissal,
  so multi-fielder run-out involvement isn't separately credited. Consistent with the data model.
- **OBS-3:** The appearance calculator's union includes `wicketkeeper_person_id` but not
  `wicketkeeper2_person_id`; a second keeper who did not bat, bowl, field or captain would not receive
  an appearance. Rare edge case.
- **OBS-4:** `competition_points.ladder` duplicates the literal `('approved','verified_partial')`
  instead of referencing `matches.VERIFIED_STATUSES` (maintainability only; values currently match).
