"""OneStats AutoSync (Phase 9) — automatic online discovery & synchronisation.

Built on the Phase 8 import pipeline and the Stage 8.9 sync interfaces; AutoSync is another controlled
entry point, never a competing system. This package holds the background job engine (``jobs``) and,
in later stages, the source registry, discovery, review queue and dashboard services.
"""
from __future__ import annotations

from onestats.domain.autosync import jobs

__all__ = ["jobs"]
