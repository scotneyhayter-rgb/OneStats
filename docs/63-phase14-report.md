# Phase 14 — Ask OneStats: Implementation Report

**Status: IMPLEMENTED — AWAITING COMBINED MANUAL ACCEPTANCE (deferred to after Phase 17).**
Not recorded as formally user-accepted. Phase 14 manual tests are registered in
[62-deferred-acceptance-register.md](62-deferred-acceptance-register.md).

Built on deliverable 28 (Ask OneStats) and the Phase 12 Report Catalogue. **Language in, deterministic
query out** — the NL layer only maps a question to a catalogue report + scope; every number comes from the
one engine. No LLM and no external service (deliverable 28.3 approach 1); nothing is fabricated.

## What was implemented

- **`domain/ask.py`** — a rule/grammar + synonym mapper. ~50 ordered metric rules map a question to one of
  the 79 catalogue reports (most runs, most wickets, best average/economy, centuries, catches, stumpings,
  partnerships, captaincy win %, consecutive records, etc.). Scope is extracted separately and applied as a
  **filter** (never a different report): Grand Finals / Finals, home/away, and a named season. A streak
  question phrased about "the captain" is disambiguated to the captaincy streak. The answer carries the
  interpretation ("I read this as …"), a plain-language headline from the No. 1 row, the report table from
  the engine, and the report's qualifications + the approved-only/known-minimum caveat.
- **No fabrication** — a question that cannot be confidently mapped returns `matched: false` with the
  nearest supported reports (ranked by word overlap), never a guessed number.
- **API** — `POST /workspaces/{id}/ask` (`ask.py` router), permission-gated (`match.view`) and
  workspace-scoped; the engine runs on approved data only.
- **Desktop** — the Ask OneStats screen (`features/ask/Ask.tsx`, replacing the placeholder): a question
  box, example questions, the answer card (headline, interpretation, the report table, confidence, and
  qualifications), and a clear "couldn't map — nearest reports" state. Reachable from the primary nav.

## Guardrails (deliverable 28.4)

- Permission + workspace scope enforced by the endpoint before the engine runs.
- Qualifications/known-minimum caveats travel with every answer; the figures are the engine's.
- Insufficient data → "no verified data matches" / clarify, never a guess.
- Reproducible: the same question maps to the same report spec → the same result.

## Automated test results

- Backend `tests/test_ask.py` (7): most-runs maps + correct No. 1; **most wickets in grand finals** applies
  the GF filter (5, not 8); captain win-% maps; consecutive-captain-wins disambiguation; partnership maps;
  an unmappable question does **not** fabricate (offers suggestions); answers carry qualifications + a
  headline.
- Desktop `features/ask/ask.test.tsx` (2): a mapped question renders the table + qualifications; an
  unmapped question shows the nearest reports.
- Full suites green; `ruff` + `tsc` clean. (Backend total recorded in the commit.)

## Risks & limitations

- The mapper is **deterministic and finite** by design — it understands the RMCC/catalogue question set and
  common phrasings, not arbitrary free text. Unrecognised phrasings are handled safely (nearest reports),
  never with a wrong number.
- Player-specific questions ("how many runs has X scored?") currently map to the relevant leaderboard, not a
  single-player answer; a future enhancement can resolve a named person to their profile figures.
- **Optional future (user-gated):** an LLM could translate free text into a *validated* report spec behind
  the same deterministic boundary (deliverable 28.3 approach 2). This needs a model (local or API) and is a
  **privacy/paid-service decision for the user** — not implemented, and not required for Phase 14.

## Readiness

Phase 14 is complete and ready for the post-Phase-17 consolidated manual acceptance. **No phase is marked
user-accepted.** Proceeding to **Phase 15 — Website Publishing & Sync** (including mandatory individual
report publishing, §29.6) next, per the approved sequence.
