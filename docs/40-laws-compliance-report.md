# 40. Laws of Cricket — Compliance & Compatibility Report

**Deliverable 40.** Review & documentation only. Reviews the OneStats Phase 6
Matches & Scorecards architecture (Stages 1–3 implemented; Stages 4–8 planned) against the
MCC Laws of Cricket, **2017 Code, 4th Edition (2026)**, effective 1 October 2026. Reference
register: [39. Laws of Cricket Reference](39-laws-of-cricket-reference.md).

> **No code, schema or migration was changed by this review.** Every item that would change
> completed Stage 1/2 behaviour is listed under §40.6 "Decisions requiring approval" and is
> **not** actioned.

## 40.0 Summary verdict

| Area | Verdict |
|---|---|
| Results & innings (Stage 1/2) | ✅ Compatible with Law 13/15/16 |
| Runs & extras (Stage 2) | ✅ Compatible with Law 18/21/22/23/41 |
| Wickets & dismissals (Stage 3) | ✅ Compatible with Law 32–40; taxonomy richer than the Laws (by design) |
| Retirements & substitutes | ✅ Compatible with Law 24/25.4 |
| Batting/bowling/fielding attribution | ✅ (batting/fielding) · ⏳ bowling is Stage 4 |
| Overs & valid deliveries | ⏳ Deferred to Stage 4 (not yet built) — **gap, not a defect** |
| Scorecard reconciliation | ⚠️ Partial — innings-total reconciliation exists; full cross-check needs Stages 4–5 |
| No retrospective application | ⚠️ Principle sound; **governing-edition capture is a recommended addition** (§40.4/40.6) |

**Bottom line:** the implemented work (Stages 1–3) is **compatible** with the 2026 Laws and
required no retrospective assumptions. The gaps are all in *not-yet-built* stages or in
*optional provenance enrichment*, and the one cross-cutting recommendation (recording the
governing Code/edition per match) is additive and needs your approval before implementation.

## 40.1 Confirmed compatibility

**Results & innings (Law 13, 15, 16) — Stage 1 `match`, Stage 2 `innings`.**
- `RESULT_TYPES = home_win, away_win, tie, draw, no_result, abandoned, washout, forfeit,
  unknown` correctly distinguishes a **tie** (Law 16.3, completed, scores level) from a
  **draw** (Law 16.4, time expired, not completed) — a distinction the Laws insist on and
  that many systems get wrong. ✅
- Margin is stored as `margin_runs` **or** `margin_wickets` with `won_by_team_id`, matching
  Law 16.5 (side batting last wins → by wickets; otherwise → by runs). ✅
- Forfeiture (Law 15.2) is representable both as an innings `status = forfeited` (Stage 2)
  and a match `result_type = forfeit` (Stage 1). ✅
- Declaration (Law 15.1) → innings `status = declared`. ✅
- Multiple innings per match and per-innings batting/bowling sides (Law 13) → `innings`
  table keyed by `inns_number`. ✅

**Runs & extras (Law 18, 21, 22, 23, 41) — Stage 2 `innings`.**
- All five extra classes are modelled exactly: `byes` (Law 23), `legbyes` (Law 23),
  `wides` (Law 22), `noballs` (Law 21), `penalty` (Law 41/18.5 penalty runs). ✅
- Every extra is **nullable = unknown**, never defaulted to 0 (deliverable 13.3) — so a card
  that records only "byes 4" does not assert "0 wides". ✅
- Innings total is **derived** (batting runs + extras), with an optional **official
  override** stored separately and never overwriting source — this matches the real
  CricketStatz model and keeps source / calculated / official as three distinct layers
  (deliverable 13.6). ✅

**Wickets & dismissals (Law 32–40) — Stage 3 `batting_entry`.**
- Every Lawful mode of dismissal maps to a canonical type: `bowled` (32), `caught` (33),
  `hit_twice` (34), `hit_wicket` (35), `lbw` (36), `obstructing` (37), `run_out` (38),
  `stumped` (39), `timed_out` (40). ✅
- Participation/status axes the Laws imply are modelled: `not_out`, `dnb`, `absent`,
  `retired_not_out`, `retired_out`, plus `unknown_out` (out, manner unknown) and `unknown`.
  Wicket counting correctly **excludes** not-out/dnb/absent/retired-not-out/unresolved and
  **includes** `unknown_out`. ✅
- The original source dismissal code is preserved verbatim (`dismissal_source_code`) and the
  mapped type never overwrites it — essential for historical fidelity and for not applying
  modern mappings retrospectively (§39.5). ✅

**Retirements & substitutes (Law 24, 25.4).**
- Law 25.4's two outcomes (retired–out vs retired–not out) plus an unresolved case are all
  modelled; the batting-average treatment follows the Law. ✅
- Fielding attribution (`fielder_person_id`) is a free person reference, so a **substitute
  fielder** (Law 24) who takes a catch or effects a run-out can be credited even though they
  are not in the batting/bowling XI. ✅

**Attribution (Law 27, 28, 33, 38, 39).**
- Batting identity + order, bowler attribution on a dismissal (`bowler_person_id`) and
  fielder/keeper attribution (`fielder_person_id`) are all stored. Keeper-vs-fielder credit
  correctly keys on "fielder is the recorded wicketkeeper" rather than on a dismissal code
  (deliverable 16 §16.8), matching how real data is recorded. ✅ (bowling figures
  themselves are Stage 4.)

## 40.2 Potential gaps

| # | Gap | Law | Severity | Where it belongs |
|---|---|---|---|---|
| G1 | **Overs & valid deliveries not yet modelled** — no over count / valid-ball count on `innings`; over notation (5.3) and balls-per-over conversion are specified but unbuilt | 17, 21.18, 22.6 | Expected | **Stage 4 (Bowling)** — build with Law 17 refs |
| G2 | **Full scorecard reconciliation incomplete** — innings total reconciles (extras + derived); batting-vs-bowling-vs-FOW cross-checks need bowling (Stage 4) and FOW (Stage 5) | 18, 32–40 | Expected | **Stages 4–5** |
| G3 | **Governing Code/edition not recorded per match** — OneStats keys validity to `match_date` but does not persist *which* Code/edition/playing-conditions version governed the match | §39.5 | Advisory | Cross-cutting — **approval item D-LAW-1** |
| G4 | **No-ball / wide run composition not separable** — extras are per-innings aggregates (matches CS); runs scored off a no-ball vs the no-ball penalty are not separable | 21.18, 22.6 | Low | Accept (matches source); document as a recording convention |
| G5 | **Follow-on not explicitly flagged** (Law 14) — derivable from innings order but not a stored attribute | 14 | Low | Optional Stage 4/5 attribute |
| G6 | **Timed-out limit is a playing condition, not a constant** — the minutes allowed differ by era/competition; OneStats must read it from `playing_condition`, never hardcode | 40 | Advisory | Stage 4+ validation; already the intended pattern |
| G7 | **2026 sub-clause numbers unverified in full** — the 4th-Edition PDF has not been read end-to-end; a handful of exact sub-clauses (e.g. overthrow wording) are provisional | 12.5.2, 19.8 | Low | Recommended follow-up (§40.5) |

None of G1–G7 is a defect in completed work; G1/G2/G5 are simply future stages, and
G3/G6/G7 are additive/advisory.

## 40.3 Historical considerations

- **Earlier Codes.** Matches before 1 Oct 2017 are governed by the 2000/1980/earlier Codes.
  Dismissal modes, extras treatment and even available results differ (e.g. pre-2017
  "handled the ball" is a distinct mode). OneStats must not assume the 2017 Code for them.
- **Unknown ≠ zero, and unknown edition ≠ modern edition.** Just as a blank statistic is
  unknown rather than 0, an unknown governing edition must downgrade checks to advisory, not
  assume "today's Laws".
- **Preserve original terms.** `dismissal_source_code` already keeps the source code
  verbatim; the same discipline should extend to any historical term that does not map
  cleanly (map + flag, never rewrite).
- **Era-dependent limits.** Balls per over (4/6/8-ball overs historically), overs per
  innings, team sizes and timed-out minutes are all era/competition dependent and already
  belong in `playing_condition` — validation must read them, never hardcode a modern value.
- **Newspaper / partial sources.** Historical cards frequently record only runs and a
  dismissal word, no balls, no fielder. The nullable model and non-blocking validation
  already support this; the Laws review does not change it.

## 40.4 Where OneStats should warn / validate / configure — not reject

Every Law-derived check is **advisory or configurable**. The table records the Law reference
alongside the proposed rule (requirement 6). All are **warnings**, never hard rejections, so
legitimate historical oddities still save.

| Proposed rule (advisory / configurable) | Law ref | Behaviour | Status |
|---|---|---|---|
| Genuine wickets in an innings > 10 | 13 | Warn (`more_than_10_wickets`) | ✅ already in Stage 3 `validation_warnings` |
| Bowler credited on a non-bowler dismissal (run out, obstruct, etc.) | 32–39 | Warn (`bowler_on_non_bowler_dismissal`) | ✅ already in Stage 3 |
| Fielder credited where the mode carries no fielder credit | 33/38/39 | Warn (`fielder_on_non_fielder_dismissal`) | ✅ already in Stage 3 |
| Unresolved dismissal (retired/unknown) needs confirmation | 25.4 | Warn (`dismissal_unresolved`), never guess | ✅ already in Stage 3 |
| Official innings total < sum of recorded extras | 18/23 | Warn (`official_total_less_than_extras`) | ✅ already in Stage 2 |
| Derived total ≠ official total | 18 | Informational; keep both | ✅ already in Stage 2 |
| Innings overs > configured overs-per-innings | 17 + playing conditions | Warn, read limit from `playing_condition` | ⏳ Stage 4 |
| Valid deliveries in an over ≠ balls-per-over (allowing wides/no-balls) | 17/21/22 + PC | Warn, configurable | ⏳ Stage 4 |
| Batting runs + extras ≠ bowling runs conceded | 18 | Warn (reconciliation) | ⏳ Stage 4 |
| Sum of partnership/FOW runs inconsistent with total | 18 | Warn | ⏳ Stage 5 |
| Timed-out applied where the mode/limit doesn't fit the era | 40 + PC | Warn, read limit from `playing_condition` | ⏳ Stage 4+ |

Design principle confirmed: **validation guides the researcher; it never blocks recording a
documented historical fact.**

## 40.5 Recommended improvements

1. **R1 — Record the governing Code/edition per match (approval item D-LAW-1).** Add an
   optional `laws_code` / `laws_edition` (or a single provenance field) to `match`, defaulted
   to unknown, shown in the UI, and used to select which limits/terminology apply. Additive,
   nullable, no backfill. *Needs approval (§40.6).*
2. **R2 — Centralise Law references in validation messages.** Where a warning maps to a Law,
   include the Law number (e.g. "more_than_10_wickets (Law 13)") so researchers see the
   basis. Low-risk, additive to message text; can fold into Stage 4.
3. **R3 — Build Stage 4 overs/valid-delivery checks against playing conditions**, citing
   Law 17/21/22, reading balls-per-over and overs-per-innings from `playing_condition`
   (never hardcoded), with over notation (5.3) preserved and balls derived via
   balls-per-over. Fold into the Stage 4 acceptance criteria (§40.7).
4. **R4 — Read the 4th-Edition PDF end-to-end** and finalise the provisional sub-clauses in
   register §39.4 (overthrow/misfield wording, last-over clause, any timed-out/substitute
   changes), upgrading them from *provisional* to *confirmed*. Documentation-only follow-up.
5. **R5 — Keep the 4-layer separation explicit in the UI** (Law vs playing condition vs
   historical edition vs statistical convention) so a user never mistakes a statistical
   convention (e.g. "caught behind") for a Law distinction.

## 40.6 Decisions requiring your approval

> These are **not** actioned. Each would touch schema or completed-stage behaviour.

- **D-LAW-1 — Governing Code/edition on `match` (R1).** Approve adding a nullable
  provenance field (new migration, e.g. `0021` ahead of Bowling, or folded into Stage 4)?
  *Recommended.* Touches the Stage 1 `match` table additively; **no backfill**, existing
  rows stay `unknown`.
- **D-LAW-2 — Law numbers in Stage 2/3 warning strings (R2).** Approve editing the existing
  `validation_warnings` message text in `innings.py` / `batting.py` to append Law numbers?
  This **modifies completed Stage 2/3 code** (message strings + their test assertions), so
  per your instruction it is flagged, not done.
- **D-LAW-3 — Scope of Stage 4 reconciliation (R3).** Confirm that Stage 4 should implement
  the overs/valid-delivery and batting-vs-bowling reconciliation warnings in §40.4, with
  Law references, before the statistics engine phase.
- **D-LAW-4 — PDF deep-read (R4).** Approve a short documentation-only follow-up to finalise
  the provisional 2026 sub-clauses in §39.4.

**No compatibility break was found in Stages 1–3.** D-LAW-2 is the only item that would
change completed code, and it is cosmetic (message text); everything else is additive or
belongs to unbuilt stages.

## 40.7 Incorporation into remaining Phase 6 planning & acceptance criteria

Law references added to the already-approved remaining stages (acceptance criteria; subject
to the normal per-stage approval):

| Stage | Add to acceptance criteria | Law refs |
|---|---|---|
| **4 — Bowling (0021)** | Overs in cricket-over notation; valid-delivery count excluding wides/no-balls; overs-per-innings and balls-per-over read from `playing_condition` (never hardcoded); runs conceded reconcilable with batting runs + extras; wickets credited only for bowler-credit dismissals (no run-outs); all checks advisory | 17, 18, 21, 22, 32–36, 39 |
| **5 — FOW & partnerships (0022)** | FOW runs/positions consistent with batting; partnership runs reconcile with innings total (warn, not block); unbeaten partnerships handled | 18 |
| **6 — Finals linkage & premierships** | Result (Law 16) and classification remain independent of round labels; tie/draw/forfeit handled per Law 16/15 | 15, 16 |
| **7 — Manual scorecard entry UI** | Surface advisory warnings inline (not blockers); expose the 4-layer distinction (Law/PC/edition/convention); allow recording documented oddities | all |
| **8 — CricketStatz import** | Preserve source dismissal/result/extra codes verbatim; map + flag, never guess; never apply modern Laws to historical imports (§39.5) | all |
| **Cross-cutting** | If D-LAW-1 approved: capture governing Code/edition per match and drive era-appropriate validation | §39.5 |

**Sources:** see register [§39](39-laws-of-cricket-reference.md) for the full MCC citation list.
