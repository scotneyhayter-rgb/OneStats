"""Phase 9 (AutoSync) service interfaces — defined in Phase 8, Stage 8.9.

This is the seam Phase 9's automatic online discovery will plug into. It does NOT build a discovery
engine; it defines the reusable contracts and a thin orchestrator so that scheduled online sources,
when they exist, flow through the SAME validation, matching (dedupe), import, approval and
recalculation services the manual importer uses — never a parallel path.

A Phase 9 source implements :class:`SyncSource` (adapter-backed: it knows how to fetch new/updated
matches as a Canonical dataset, and tracks a watermark for offline catch-up). The orchestrator
imports as draft and, only in ``authorised_automatic`` mode AND with the approver permission, approves
and recalculates — otherwise everything waits for administrator review, exactly as a manual import.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain import matches, recalc
from onestats.domain.importing import pipeline
from onestats.domain.importing.model import CanonicalDataset

# processing modes (STEP 11): review-required vs authorised-automatic
REVIEW_REQUIRED = "review_required"
AUTHORISED_AUTOMATIC = "authorised_automatic"
SYNC_MODES = (REVIEW_REQUIRED, AUTHORISED_AUTOMATIC)


@dataclass(slots=True)
class SyncCursor:
    """A source's position, for offline catch-up / resuming — persisted by Phase 9, opaque here."""
    source_system: str
    last_ref: str | None = None
    last_seen_at: datetime | None = None


@dataclass(slots=True)
class SyncBatch:
    """What a source yields on a poll: a Canonical dataset plus the advanced cursor."""
    dataset: CanonicalDataset
    cursor: SyncCursor


@runtime_checkable
class SyncSource(Protocol):
    """A Phase 9 online source. Phase 8 defines the contract only; no implementation discovers data."""
    source_system: str
    format_id: str

    def fetch_new(self, since: SyncCursor | None) -> SyncBatch:
        """New matches since the cursor (as a Canonical dataset), plus the advanced cursor."""

    def fetch_updated(self, since: SyncCursor | None) -> SyncBatch:
        """Matches whose scorecards changed since the cursor."""


@dataclass(slots=True)
class SyncJob:
    """A scheduled sync job's configuration (descriptor only — not executed in Phase 8)."""
    workspace_id: UUID
    source_system: str
    schedule: str                      # cron-like, interpreted by Phase 9's scheduler
    mode: str = REVIEW_REQUIRED
    enabled: bool = True
    cursor: SyncCursor | None = None
    options: dict[str, Any] = field(default_factory=dict)


def process_sync_batch(
    conn: Connection, workspace_id: UUID, actor: str, dataset: CanonicalDataset, *,
    mode: str = REVIEW_REQUIRED, can_approve: bool = False,
) -> dict[str, Any]:
    """Run one batch through the shared pipeline: import as draft, then — only in
    ``authorised_automatic`` mode and when the actor may approve — approve the imported matches and
    recalculate official statistics. Otherwise everything stays draft for administrator review. This
    is the one place Phase 9 needs to call; it reuses the manual importer's services unchanged.

    Returns the import result plus how many matches were auto-approved (0 unless authorised)."""
    if mode not in SYNC_MODES:
        raise ValueError("invalid_sync_mode")
    result = pipeline.import_dataset(conn, workspace_id, actor, dataset=dataset, commit=True)
    source_system = dataset.provenance.source_system

    approved = 0
    if mode == AUTHORISED_AUTOMATIC and can_approve:
        # approve exactly the matches this batch imported; approval drives the recalculation ledger
        for m in dataset.matches:
            mid = conn.execute(
                text("SELECT id FROM match WHERE source_system = :ss AND source_ref = :sr"),
                {"ss": source_system, "sr": m.source_ref},
            ).scalar_one_or_none()
            if mid is None:
                continue
            matches.set_approval(conn, workspace_id, actor, mid, status="approved",
                                 reason="auto-approved by authorised AutoSync")
            recalc.recompute_match(conn, workspace_id, actor, mid)
            approved += 1

    return {"imported": result, "mode": mode, "auto_approved": approved,
            "review_required": mode == REVIEW_REQUIRED or not can_approve}
