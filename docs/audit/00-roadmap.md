# OneStats ↔ CricketStatz Audit — Roadmap & Status

Master prompt: a comprehensive comparison of OneStats against CricketStatz (the trusted numeric benchmark),
to make OneStats a *superior* platform — not a clone. Staged, with implementation of substantial features
gated on the user's approval. Verified statistical bug fixes may proceed immediately where safe.

## Guardrails (from the prompt)
- CricketStatz is the numeric reference, not a product to copy. No proprietary code/graphics/layout.
- Only authorised, read-only access and permitted exports. Never alter the CricketStatz database.
- Never invent statistics; unknown ≠ zero. Preserve approved historical records, RLS/workspace isolation,
  and the agreed forfeit/captaincy/partnership rules. Keep the 79-report catalogue unless change is justified.
- Exclude CricketStatz Captain2 (prior decision). Don't rebuild the Windows installer during this exercise.
- Don't claim internal tests prove CricketStatz parity.

## Stages & status

| Stage | Scope | Status |
|---|---|---|
| 1. Discovery | Inventory CricketStatz + OneStats capabilities | **CricketStatz side captured** → [01-cricketstatz-capability-inventory.md](01-cricketstatz-capability-inventory.md). OneStats side: TODO |
| 2. Filtering analysis | CricketStatz filter model; design OneStats universal filter | CricketStatz model captured (Deliverable A §2). Proposal (C): TODO |
| 3. Report analysis | Report-by-report CricketStatz vs OneStats | CricketStatz catalogue captured (A §3). Comparison (D): TODO |
| 4. Statistical reconciliation | Numeric comparison on equivalent data+filters | Run-outs done (see below). Broader: TODO |
| 5. Correct critical defects | Fix verified calc/validation/integrity bugs + tests | **In progress** — run-out attribution fixed (commit f0b3bff) |
| 6. Recommendations | Prioritised roadmap (Deliverables F–J) | TODO |
| 7. Implement approved items | Only after user approves the programme | Not started (gated) |

## Deliverables (A–J) — tracking
- **A** Capability inventory — CricketStatz captured (doc 01). OneStats side pending.
- **B** Filtering analysis — captured in doc 01 §2; write-up pending.
- **C** OneStats universal filtering proposal — pending (design for approval).
- **D** Report comparison — pending (needs OneStats catalogue pull).
- **E** Statistical accuracy report — pending; run-out reconciliation complete.
- **F** Workflow/usability — pending.
- **G** Recommended new capabilities — seeded in doc 01 §4.
- **H** Prioritised roadmap — this file will grow into it.
- **I** Implementation readiness — pending.
- **J** Executive summary — pending (final).

## Confirmed defects fixed (Stage 5)
1. **Run-out fielder attribution undercounted.** OneStats faithfully reproduced a *stale* CricketStatz export
   that omitted fielders the scorer added later (Hayter 13 vs 18; Robinson R 0 vs 2, etc.). Fix: a fielder
   backfill that copies newly-known fielders from a fresher re-import onto existing matches and recomputes,
   without overwriting manual corrections. Commit **f0b3bff**; regression test
   `test_backfill_fills_fielders_added_to_source_after_original_export`. Full analysis in the session notes.

## How this proceeds
Each future turn advances one or more stages and updates this file. Nothing in Stage 7 (major UI/feature
work such as the universal filter bar or new reports) is built until the Stage 6 roadmap is approved.
