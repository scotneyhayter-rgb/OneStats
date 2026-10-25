"""Universal third-party import framework (Phase 8).

An adapter-based layer over the existing (already source-agnostic) staging substrate. Source adapters
turn a file into the Canonical Cricket Data Model (``model``); the shared core pipeline then stages,
matches, validates, previews, commits and records provenance — identically for every source. The
CricketStatz importer is the first adapter (Stage 8.2); CSV/Excel/JSON/XML follow.

Nothing here fabricates data: unknown stays unknown (never 0), identities are never auto-merged,
provenance is preserved, and imported scorecards remain draft until approved (Phase 7 authority).
"""
from __future__ import annotations

from onestats.domain.importing import model
from onestats.domain.importing.adapter import (
    AdapterRegistry,
    SourceAdapter,
    detect_adapter,
    get_adapter,
    register_adapter,
    registry,
)

__all__ = [
    "AdapterRegistry",
    "SourceAdapter",
    "detect_adapter",
    "get_adapter",
    "model",
    "register_adapter",
    "registry",
]
