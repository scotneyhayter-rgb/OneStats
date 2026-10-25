"""Reusable column-mapping engine for generic tabular/structured sources (Phase 8, Stage 8.3).

CSV/Excel/JSON/XML exports vary in their column names, so a generic adapter takes a **mapping
template** — a named set of ``canonical field -> source column`` rules with a value kind — and applies
it to each source row. Blank/absent values become ``None`` (unknown is never coerced to zero), and a
user-confirmed override map can replace the defaults in the wizard.

This engine never invents data: a column that isn't present yields ``None``; a value that can't be
coerced yields ``None`` (the raw text is still recoverable from the staged source row).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

Kind = str  # "str" | "int" | "float" | "date" | "bool"


def coerce(value: Any, kind: Kind) -> Any:
    """Coerce a raw cell to ``kind``; blank/unparseable → ``None`` (never 0/"" as a stand-in)."""
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        if value == "":
            return None
    if kind == "str":
        return str(value)
    if kind == "int":
        try:
            return int(value)
        except (TypeError, ValueError):
            try:
                return int(float(value))
            except (TypeError, ValueError):
                return None
    if kind == "float":
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    if kind == "bool":
        s = str(value).strip().lower()
        if s in ("1", "true", "yes", "y"):
            return True
        if s in ("0", "false", "no", "n"):
            return False
        return None
    if kind == "date":
        if isinstance(value, date):
            return value
        s = str(value).strip()
        for fmt in _DATE_FORMATS:
            try:
                return _parse_date(s, fmt)
            except ValueError:
                continue
        return None
    raise ValueError(f"unknown coercion kind: {kind}")


_DATE_FORMATS = ("iso", "dmy", "mdy")


def _parse_date(s: str, fmt: str) -> date:
    if fmt == "iso":
        return date.fromisoformat(s[:10])
    sep = "/" if "/" in s else "-" if "-" in s else "."
    parts = s.split(sep)
    if len(parts) != 3:
        raise ValueError("not a 3-part date")
    a, b, c = (int(p) for p in parts)
    if fmt == "dmy":
        return date(c if c > 31 else 2000 + c if c < 100 else c, b, a)
    if fmt == "mdy":
        return date(c if c > 31 else 2000 + c if c < 100 else c, a, b)
    raise ValueError("unhandled date format")  # pragma: no cover


@dataclass(slots=True)
class FieldRule:
    """One ``canonical_field`` fed from a source ``column`` coerced to ``kind``."""
    canonical: str
    column: str
    kind: Kind = "str"


@dataclass(slots=True)
class MappingTemplate:
    """A named set of field rules for one entity kind (e.g. a match-summary CSV row)."""
    name: str
    entity: str
    rules: list[FieldRule] = field(default_factory=list)

    def apply(self, row: dict[str, Any], *, overrides: dict[str, str] | None = None) -> dict[str, Any]:
        """Map one source row to ``{canonical_field: value}``. ``overrides`` remaps a canonical field
        to a different source column (what the wizard captures when columns don't match the default)."""
        out: dict[str, Any] = {}
        for rule in self.rules:
            column = (overrides or {}).get(rule.canonical, rule.column)
            out[rule.canonical] = coerce(row.get(column), rule.kind)
        return out


def slugify(value: Any) -> str | None:
    """A stable source ref for a source that has no ids (CSV/Excel): lowercased, trimmed, spaces and
    punctuation collapsed to single hyphens. Blank → ``None``. Deterministic, so re-importing the same
    file yields the same refs (idempotent matching)."""
    if value is None:
        return None
    s = re.sub(r"[^a-z0-9]+", "-", str(value).strip().lower()).strip("-")
    return s or None
