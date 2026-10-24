# CricketStatz `Howout` Dismissal-Code Legend (Phase 6, Stage 8b)

The reusable mapping from CricketStatz `Howout` codes to OneStats `dismissal_type`, used by the
CricketStatz import adapter for **all** imports. The raw code is always preserved on every batting
record in `dismissal_source_code`; any code **not** in the verified table stays **unresolved**
(`dismissal_type` NULL) for administrator review — nothing is guessed, and `did not bat` is never
treated as a dismissal.

## Source of the legend

1. **Authoritative:** the official CricketStatz API documentation
   (cricketstatz.com/api-for-uploading-matches) publishes the `Howout` enumeration.
2. **Corroboration:** the structural evidence in the genuine export agrees with it for every code —
   the bowler/fielder fields present on each dismissal match the expected pattern (see the evidence
   column below).
3. **Prior OneStats fixtures** already used `2→bowled`, `3→caught`, `6→lbw`, `7→run_out`.

These three independent lines of evidence agree, which is why the implemented codes are rated High.

## Implemented mapping (`imports.CS_HOWOUT`)

| Code | CricketStatz | OneStats `dismissal_type` | Wicket? | Evidence (export) | Confidence |
|---|---|---|---|---|---|
| 0 | did not bat | `dnb` | no | 100% zero score/balls; no bowler/fielder | High |
| 1 | not out | `not_out` | no | 0% bowler, 0% fielder, never in a fall of wicket | High |
| 2 | bowled | `bowled` | yes | 96.5% bowler, **0% fielder** | High |
| 3 | caught | `caught` | yes | 99% bowler **+** 97% fielder (catcher) | High |
| 6 | lbw | `lbw` | yes | 99.6% bowler, **0% fielder** | High |
| 7 | run out | `run_out` | yes (no bowler credit) | ~1% bowler, fielder sometimes | High |
| 8 | stumped | `stumped` | yes | 99.6% bowler **+** 97% fielder (keeper) | High |
| 20 | retired | `retired_not_out` | **no** | retired hurt/ill — distinct from retired out | High |
| 21 | absent | `absent` | no | non-wicket | High |
| 22 | retired out | `retired_out` | **yes** | a genuine dismissal (chose not to resume) | High |

Codes **2 vs 6** (both bowler-only) and **3 vs 8** (both bowler+fielder) are structurally identical
and are distinguished *only* by the code number via the authoritative legend.

## Deliberately left UNRESOLVED (preserved, not mapped)

| Code | CricketStatz | Why unresolved |
|---|---|---|
| 4 | caught & bowled | Documented & evidenced, but outside the approved six — awaiting confirmation. |
| 5 | caught behind | As above (bowler + keeper pattern). |
| 9 | hit wicket | As above (bowler-only). |
| 10 | obstructed | Rare (1 in export); confirm before mapping to `obstructing`. |
| 12 | hit twice | Not seen in export; would map to `hit_twice`. |
| 23 | timed out | Rare (1); would map to `timed_out`. |
| 11 | handled ball | **No exact OneStats type** (modern Laws fold it into obstructing) — kept raw. |
| 24 | *(undocumented)* | Not in the CricketStatz legend at all — genuinely unknown. |

Unmapped codes keep their `dismissal_source_code` and can be mapped later in bulk via
`imports.remap_howout_dismissals` — **no re-import required.**

## Applying it

- **New imports:** `imports.map_howout(code)` is applied during promotion; unmapped → NULL + flagged.
- **Existing rows:** `imports.remap_howout_dismissals(conn, workspace_id, actor)` fills `dismissal_type`
  in place where it is still NULL and the code is verified — never overwriting a type already set,
  never creating rows, fully audited.
