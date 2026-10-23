# 39. Laws of Cricket — Authoritative Reference Register

**Deliverable 39.** Review/reference document. Establishes the authoritative Laws of
Cricket reference for OneStats validation, scorecard reconciliation and terminology.
Paired with the compliance review in [40. Laws of Cricket Compliance & Compatibility
Report](40-laws-compliance-report.md).

> **Status:** reference only. This register does **not** change any schema, migration or
> code. Nothing here is applied retrospectively to historical matches (see §39.5).

## 39.1 Authoritative edition register

| Field | Value |
|---|---|
| **Code** | The Laws of Cricket, **2017 Code** |
| **Edition in force** | **4th Edition (2026)** |
| **Effective date** | **1 October 2026** |
| **Custodian** | Marylebone Cricket Club (MCC) |
| **Primary source** | https://www.lords.org/mcc/about-the-laws-of-cricket |
| **Full text (4th Ed. PDF)** | https://www.lords.org/getmedia/1d908298-5c44-468d-b6a7-e1414a1296e0/Laws-of-Cricket-2017-Code-4th-Edition-(2026)_3.pdf |
| **Scale of change** | ~73 material changes vs the 3rd Edition, plus gender-neutral language throughout |
| **Retrieved** | 2026-10-24 (OneStats research task) |

### Edition lineage (the 2017 Code and its editions)

| Edition | Published / effective | Notes |
|---|---|---|
| 2017 Code, 1st Edition | 1 October 2017 | Major recodification; "handled the ball" merged into *Obstructing the field*; sanctions/send-offs (Law 42) introduced |
| 2017 Code, 2nd Edition | April 2019 | Clarifications |
| 2017 Code, 3rd Edition | October 2022 | "batsman" → "batter"; non-striker run-out moved to Law 38 (Run out) in the Jan 2023 update |
| **2017 Code, 4th Edition** | **1 October 2026** | ~73 changes — see §39.4 |

> Earlier **Codes** (2000 Code, 1980 Code, and pre-1980 Codes back to 1744) governed
> historical matches and differ materially. OneStats must never assume the 2017 Code for a
> match played before 1 October 2017 (§39.5).

## 39.2 Law-number index relevant to OneStats

Stable 2017-Code Law numbers that OneStats records or reconciles against. (Numbers are
unchanged across the 2017-Code editions; only wording/sub-clauses changed.)

| Law | Title | Where OneStats touches it |
|---|---|---|
| 1 | The players | Team size (playing conditions), XI / substitutes |
| 2 | The umpires | `match_official` |
| 3 | The scorers | Provenance, scorer officials |
| 4 / 5 | The ball / The bat | Equipment (not modelled; 2026 changes, §39.4) |
| 12 | Start of play; cessation of play | **12.5.2** last over of day (changed 2026) |
| 13 | Innings | Stage 2 `innings`, `inns_number`, multiple innings |
| 14 | The follow-on | Innings sequence (derivable; not yet modelled) |
| 15 | Declaration and forfeiture | Stage 2 `innings.status = declared`; Stage 1 `result_type = forfeit` |
| 16 | The result | **Stage 1** `result_type`, `won_by_team_id`, `margin_runs`/`margin_wickets`; tie vs draw |
| 17 | The over | **Stage 4** overs, valid-delivery count, over notation (5.3 = 5 overs 3 balls) |
| 18 | Scoring runs | Stage 3 batting `runs`; short runs; overthrows (19.8) |
| 19 | Boundaries | Boundary 4s/6s (Stage 3 `fours`/`sixes`); **19.8 overthrows** (changed 2026) |
| 20 | Dead ball | Not modelled (ball-by-ball absent); affects which runs count |
| 21 | No ball | **Stage 2** `innings.noballs` (extras) |
| 22 | Wide ball | **Stage 2** `innings.wides` (extras) |
| 23 | Bye and Leg bye | **Stage 2** `innings.byes`, `innings.legbyes` (extras) |
| 24 | Fielders' absence; substitutes | Fielding attribution by a substitute (Stage 3 `fielder_person_id`) |
| 25 | Batter's innings; runners | **25.4 retirement** — retired out vs retired–not out (Stage 3 dismissal types) |
| 27 | The wicket-keeper | Keeper catch/stumping attribution; `match_team.wicketkeeper_person_id` |
| 28 | The fielder | Fielding attribution (Stage 3 `fielder_person_id`) |
| 32 | Bowled | Stage 3 `dismissal_type = bowled` |
| 33 | Caught | `caught`, `caught_behind`, `caught_and_bowled` (all Law 33 — see §39.6) |
| 34 | Hit the ball twice | `hit_twice` |
| 35 | Hit wicket | `hit_wicket` |
| 36 | Leg before wicket (LBW) | `lbw` |
| 37 | Obstructing the field | `obstructing` (absorbs pre-2017 "handled the ball") |
| 38 | Run out | `run_out` (incl. non-striker run-out since 2022/Jan-2023) |
| 39 | Stumped | `stumped` |
| 40 | Timed out | `timed_out` |
| 41 | Unfair play | Penalty runs → **Stage 2** `innings.penalty`; (ball-tampering etc. not modelled) |
| 42 | Players' conduct | Not modelled (send-offs don't affect the scorecard totals) |

## 39.3 Four distinct layers (never conflate)

A deliberate separation that governs every validation rule OneStats writes:

1. **MCC Laws of Cricket** — the universal framework above. The *default* vocabulary and
   reconciliation logic (what a dismissal is, what an extra is, how a result is defined).
2. **Competition-specific playing conditions** — per-competition overrides that sit on top
   of the Laws: balls per over, overs per innings, team size, bonus/points systems, finals
   formats, interval/timed-out limits, concussion/substitute replacements, DLS, etc. In
   OneStats these live in `playing_condition` (Phase 4, migration 0008) and resolve
   match → grade → season → competition. **Playing conditions, not the Laws, decide the
   numeric limits OneStats validates against.**
3. **Historical editions and rules** — the Code/edition in force *when the match was
   played* (§39.1 lineage). A pre-2017 match is governed by an earlier Code; limits,
   terminology and even available dismissal modes differ.
4. **Statistical recording conventions** — how scorers and statisticians record and
   classify facts that the Laws do not themselves prescribe: e.g. splitting Law 33 *Caught*
   into "caught behind" (keeper) vs "caught" (fielder) vs "caught & bowled"; the
   batting-average "not out" denominator; ducks; strike rate shown only where balls are
   known. These are OneStats/statistics-engine conventions (deliverables 22–25), **not**
   Laws, and are flagged as such.

## 39.4 Confirmed 2026 (4th Edition) changes relevant to OneStats

Only changes that could touch scorecard recording/reconciliation are listed. Law numbers
are given where confirmed by the source; where the announcement gave no number it is marked
*(number per full text)*.

| Change | Law | OneStats relevance |
|---|---|---|
| **Last over of the day** continues after a wicket (multi-day): if a wicket falls with balls remaining before scheduled close, the over is completed rather than stumps drawn | **12.5.2** | Affects over/ball counts at an innings boundary in multi-day matches — a **Stage 4** (overs) and verification concern, not a rejection rule |
| **Overthrows & misfields** substantially rewritten; new definitions of an overthrow and a misfield | **19.8** *(overthrows)* | Affects how boundary/overthrow runs are attributed (Law 18/19). OneStats stores aggregate runs, not deliveries, so impact is on **reconciliation guidance**, not schema |
| **Laminated bats** legal in open-age cricket | Law 5 *(number per full text)* | Equipment only — **not modelled**; no OneStats impact |
| **Ball specifications** updated (sizes 1/2/3, tolerances) | Law 4 *(number per full text)* | Equipment only — **not modelled**; no OneStats impact |
| **Gender-neutral language** throughout | all | Terminology only; OneStats already uses neutral terms ("batter", "fielder") |

> The full 73-change list and exact sub-clause numbers are in the 4th-Edition PDF (§39.1).
> This register records what is **confirmed by MCC/CA-level sources**; any validation rule
> that depends on an unconfirmed sub-clause must cite it as *provisional* until the PDF is
> read in full (a recommended follow-up, see report §40.5).

## 39.5 Golden rule — no retrospective application

**The 2026 Laws (and the 2017 Code generally) are never applied retrospectively to a
historical match without evidence.** Concretely:

- Validation uses the edition/Code and the playing conditions **in force on the match
  date** (`match.match_date` + `date_precision`), never "today's Laws".
- Where the governing Code/edition is unknown, limits are treated as **unknown** and
  checks downgrade to advisory — OneStats does **not** reject the card.
- A 2026 definition (e.g. the rewritten overthrow rule, or a modern timed-out limit) is
  **never** used to flag a pre-2026 record as wrong.
- Terminology differences (pre-2017 "handled the ball", "batsman") are preserved as
  recorded; the original source code/term is kept verbatim (Stage 3
  `dismissal_source_code`) and never rewritten to the modern mapped type.

## 39.6 Terminology reconciliation notes

- **Caught (Law 33)** is one Law. OneStats' `caught` / `caught_behind` / `caught_and_bowled`
  split is a *statistical convention* for fielding/keeper credit (layer 4), not a Law
  distinction. Real CricketStatz data often codes keeper catches as plain "Caught (3)" with
  the keeper named as fielder (deliverable 16 §16.8) — so keeper-vs-fielder credit keys on
  "fielder is the recorded wicketkeeper", not on the dismissal code.
- **Retirement (Law 25.4)** has two Lawful outcomes: *retired – out* (counts as a dismissal)
  and *retired – not out* (ill/injured/other acceptable reason; may resume, and if not,
  **not** a dismissal and **not** in the average denominator). OneStats models all three of
  `retired_out`, `retired_not_out` and an unresolved `retired`.
- **Non-striker run-out** is a **Run out (Law 38)** since the 2017 Code 3rd-Edition/Jan-2023
  update (previously Law 41 unfair play). OneStats records it as `run_out`.
- **Handled the ball** ceased to be a separate mode in the 2017 Code (merged into
  *Obstructing the field*, Law 37). Pre-2017 cards may still record it — preserve the
  source term, map to `obstructing` or `unknown_out`, and flag, never guess (§39.5).

## 39.7 How OneStats uses this register

- **Reconciliation vocabulary** — dismissal taxonomy (Stage 3), extras (Stage 2) and result
  taxonomy (Stage 1) map to the Laws above and cite the Law number in validation messages.
- **Validation, not rejection** — Law-derived checks are **advisory warnings** or
  **configurable** against playing conditions; historical scorecards are never auto-rejected
  (report §40.4).
- **Provenance** — the governing Code/edition is a property of the match date, recorded and
  shown, never assumed from the current edition.

**Sources:**
[MCC — About the Laws](https://www.lords.org/mcc/about-the-laws-of-cricket) ·
[MCC — new edition from 1 October 2026](https://www.lords.org/lords/news-stories/mcc-announces-new-edition-of-laws-from-1-october-2026) ·
[Laws of Cricket 2017 Code 4th Edition (2026) PDF](https://www.lords.org/getmedia/1d908298-5c44-468d-b6a7-e1414a1296e0/Laws-of-Cricket-2017-Code-4th-Edition-(2026)_3.pdf) ·
[NZC — 2026 changes to the MCC Laws](https://play.nzc.nz/news/2026-changes-mcc-laws-cricket)
