# OneStats — Remaining Risks & Recommendations

Companion to the full system audit (2026-10-26). This states precisely what is **not** verified, so
nothing is implied to work without evidence.

## External dependencies

| Dependency | Status | Impact |
|---|---|---|
| **OneVault** media vault | No verified API; adapter is capability-detected and reports **unavailable** | None — OneStats operates fully without it; no independently-testable feature is blocked |
| **PlayHQ** / online connectors | Documented but **not implemented** (access/structure unverified); raise `NotImplementedError` | AutoSync/online discovery cannot be marked operational until real credentials + verified access exist |

Neither may be presented as a live integration. They are correctly fenced off in code.

## Residual risks (open)

- **R-1 — `onboarding_draft` has no RLS (BUG-005).** By-design global Super-Admin wizard state, not a
  tenant data path; endpoints are Super-Admin-only and IDs are random UUIDs. *Recommendation:* add
  `created_by` scoping to `get/save/activate_draft` for defense-in-depth. Not implemented here to avoid
  destabilising the pre-workspace onboarding flow without a dedicated test.
- **R-2 — "Best Bowling in a Match" shows wickets only (OBS-1).** No runs tie-break / no "7/23" figure.
  The data to do it (BBI wickets + runs) is already in the ledger. Enhancement, not a miscalculation.
- **R-3 — Shared run-outs (OBS-2).** One fielder per dismissal is modelled; multi-fielder run-out
  involvement isn't separately credited. A data-model limitation to confirm with the user.
- **R-4 — Career economy over length.** Economy at career scope uses a single configurable over length
  (default six). A career spanning mixed six- and eight-ball eras can't resolve per-era economy from a
  single aggregate; per-season/era figures are accurate. Documented approximation.

## Areas NOT TESTED in this audit (belong to manual acceptance / later load testing)

These were **not** exercised here and must not be assumed working:

1. **Desktop click-through** of every screen (buttons, navigation, forms retaining input, empty/error
   states) — manual acceptance.
2. **Association-scale performance** under real load (thousands of matches/players, concurrent
   operations, repeated large PDF exports). The engine was optimised earlier (conditional match-join),
   but a meaningful load test was not run in this audit.
3. **Full malformed-import matrix** (missing columns, unexpected formats, interrupted/retry/partial
   imports) beyond the existing automated integrity cases.
4. **Interrupted-operation recovery** and **backend disconnect/reconnect** behaviour end-to-end.
5. **Backup → restore drill** (Phase 11 manual test 18) — manifest/checksum design reviewed only.
6. **Settings & configuration** screens — not re-audited in depth this pass.
7. **Accessibility** (keyboard navigation, focus order, contrast, screen scaling) — not measured.

## Recommended next steps

1. Proceed to the **combined Phase 11–13 manual acceptance programme**
   (`60-combined-acceptance-phase11-13.md`), which covers items 1–6 above by hand.
2. During acceptance, spot-check: a bowler with eight-ball-over matches (economy), a captain's profile
   (captaincy now populated), and a player-profile PDF (portrait, no duplication).
3. Consider R-1 (onboarding `created_by` scoping) and R-2 ("best bowling" full figures) as small,
   contained follow-ups — not blockers for acceptance.
4. **Do not begin Phase 14** until the user formally accepts the combined programme.
