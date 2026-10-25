"""OneStats deterministic statistics engine (Phase 12).

One engine over the Phase 7 approved-statistics ledger (``match_stat_contribution``). Every report,
leaderboard, record, milestone and dashboard figure is derived here — there is no competing calculation
in the frontend or per-report code. Approved data only; verified-partial within its verified scope;
unknown is never zero; performances are never double-counted; provenance (supporting matches) is
preserved; results recompute idempotently when approved scorecards change.
"""
