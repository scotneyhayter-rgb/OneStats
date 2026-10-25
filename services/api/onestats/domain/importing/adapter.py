"""Source-adapter contract and registry — Phase 8, Stage 8.1.

An adapter does three things and nothing more: **detect** whether a file is its format, **parse** the
raw bytes/text into source rows (verbatim, no interpretation), and **normalise** those rows into the
Canonical Cricket Data Model. Everything downstream — staging, matching, validation, preview, commit,
provenance, rollback, retries — is the shared core pipeline and is identical for every source.

New formats register via :func:`register_adapter`; the pipeline never needs to change to gain one.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from onestats.domain.importing.model import CanonicalDataset

# A confidence below this is treated as "not this format" by :func:`detect_adapter`.
DETECT_THRESHOLD = 0.5


class SourceAdapter(ABC):
    """Base class for a source adapter. Subclasses set ``format_id``/``display_name``/``capabilities``
    and implement ``detect``/``parse``/``normalize``."""

    #: stable machine id, e.g. "cricket_statz", "csv_scorecard", "generic_json"
    format_id: str = ""
    #: human label for the wizard
    display_name: str = ""
    #: what this adapter can carry, e.g. {"matches", "scorecards", "people", "toss"}
    capabilities: frozenset[str] = frozenset()

    @abstractmethod
    def detect(self, sample: bytes | str, filename: str | None = None) -> float:
        """Confidence in [0, 1] that ``sample`` (and optional ``filename``) is this adapter's format.
        Must be cheap and side-effect free — it may be called on many adapters for one file."""

    @abstractmethod
    def parse(self, content: bytes | str, *, filename: str | None = None) -> Any:
        """Parse the source into verbatim rows/objects. No interpretation, no normalisation — the raw
        shape is kept so it can be stored as provenance."""

    @abstractmethod
    def normalize(self, raw: Any, *, mapping: dict[str, Any] | None = None) -> CanonicalDataset:
        """Map parsed rows into the Canonical Cricket Data Model. Unknowns stay ``None``; nothing is
        invented. ``mapping`` lets generic adapters (CSV/JSON/XML) take a user-confirmed column map."""

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<SourceAdapter {self.format_id!r}>"


class AdapterRegistry:
    """A collection of adapters, keyed by ``format_id``. Pluggable: adding an adapter never touches
    the pipeline. Detection picks the highest-confidence adapter above the threshold."""

    def __init__(self) -> None:
        self._adapters: dict[str, SourceAdapter] = {}

    def register(self, adapter: SourceAdapter) -> SourceAdapter:
        if not adapter.format_id:
            raise ValueError("adapter must define a non-empty format_id")
        if adapter.format_id in self._adapters:
            raise ValueError(f"adapter already registered: {adapter.format_id}")
        self._adapters[adapter.format_id] = adapter
        return adapter

    def get(self, format_id: str) -> SourceAdapter:
        try:
            return self._adapters[format_id]
        except KeyError as exc:
            raise ValueError(f"unknown import format: {format_id}") from exc

    def all(self) -> list[SourceAdapter]:
        return list(self._adapters.values())

    def detect(self, sample: bytes | str, filename: str | None = None) -> list[tuple[SourceAdapter, float]]:
        """Every adapter's confidence for ``sample``, best first. Scores below the threshold are
        dropped so an ambiguous file simply yields no confident match (the wizard then asks the user)."""
        scored: list[tuple[SourceAdapter, float]] = []
        for adapter in self._adapters.values():
            try:
                score = float(adapter.detect(sample, filename))
            except Exception:  # noqa: BLE001 - a misbehaving adapter must not break detection
                score = 0.0
            if score >= DETECT_THRESHOLD:
                scored.append((adapter, score))
        scored.sort(key=lambda t: t[1], reverse=True)
        return scored

    def best(self, sample: bytes | str, filename: str | None = None) -> SourceAdapter | None:
        hits = self.detect(sample, filename)
        return hits[0][0] if hits else None


# The process-wide registry. Adapters register themselves at import time (Stage 8.2 onward).
registry = AdapterRegistry()


def register_adapter(adapter: SourceAdapter) -> SourceAdapter:
    """Register an adapter in the process-wide registry (returns it, so it can decorate an instance)."""
    return registry.register(adapter)


def get_adapter(format_id: str) -> SourceAdapter:
    return registry.get(format_id)


def detect_adapter(sample: bytes | str, filename: str | None = None) -> SourceAdapter | None:
    """The best-matching registered adapter for a file, or ``None`` when nothing is confident."""
    return registry.best(sample, filename)
