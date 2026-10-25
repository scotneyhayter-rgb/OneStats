# Phase 12 (deferred) — Run-out & Wicket Reconciliation

_Logged 2026-10-25 during Phase 8. **Deferred to Phase 12 (Statistics & Reporting).** Do not build
the interface during Phase 8. The underlying dismissal classification is verified during Phase 8
import regression testing, and Phase 8 imports must retain all dismissal data these calculations
need (see "Phase 8 obligations" below)._

## Scope (Phase 12)

Provide a **Run Out count** in the bowling-innings summary, linked to the batting-innings dismissal
records. Requirements:

1. Run outs count toward **wickets lost** by the batting side but are **never credited to a bowler**.
2. Display separate totals for **bowler-credited wickets**, **run outs**, and **other non-bowler
   dismissals** (stumpings are bowler/keeper context; obstruction, retired-out, timed-out, etc.).
3. **Automatically reconcile** these against the innings wickets lost.
4. Preserve **individual fielding credits** for run outs, including **multiple fielders** where the
   source supports it.
5. Handle other dismissal types correctly under the applicable **Laws of Cricket**.
6. Never **double-count** run outs or add them to individual bowling figures.
7. Preserve **imported dismissal codes** and historical source provenance.
8. Flag discrepancies as **validation warnings**, never inventing missing data.
9. Automatically **update the summary** when scorecards are corrected and **approved** (via the
   Phase 7.8 recalculation ledger).
10. **Automated tests** for all relevant dismissal classifications and reconciliation scenarios.

## Phase 8 obligations (done now, so Phase 12 has what it needs)

- **Retain every dismissal fact at import.** The Canonical model's batting entry keeps
  `dismissal_source_code` (raw source code, always), `dismissal_type` (mapped, or `None` when the
  code is unresolved — never guessed), `bowler_ref` and `fielder_ref`. Run-out (CricketStatz
  `Howout` 7) maps to `run_out`, which credits **no** bowler — the classification is verified in the
  import regression tests.
- **Fielder credit.** CricketStatz records a single `Fielder` per dismissal; it is preserved.
  Multiple-fielder run-outs will need a model extension in Phase 12 **where a source actually
  provides more than one fielder** — CricketStatz does not, so nothing is invented now.
- **Provenance.** Source code + source system are preserved end-to-end, so Phase 12 can classify and
  reconcile from the original evidence.

No bowling-summary run-out UI, totals or reconciliation is built in Phase 8.
