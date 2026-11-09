"""OneStats version & compatibility contract (single source of truth).

The desktop app, the server and the database schema are versioned independently. This module
defines the server's identity and the explicit rules a connected desktop client is checked against —
never a guess from version numbers alone. It is pure/standalone so it can be unit-tested without a
database or FastAPI.

Versioning scheme (documented in docs/74-update-system.md):
  * Server version    — semantic version of the FastAPI backend (this file).
  * Desktop version   — semantic version of the Tauri app (apps/desktop: tauri.conf.json/version.ts).
  * API version       — integer contract version; bumped only on a breaking client/server API change.
  * Database schema    — the Alembic head the server code expects (+ a numeric level for display/order).
Compatibility is decided by the API version and explicit min/max desktop rules below, not by the
marketing version string.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# --- Server identity ---
SERVER_VERSION = "1.0.0-beta.5"
API_VERSION = 1

# --- Database schema the server code expects (keep in step with the Alembic head) ---
DB_SCHEMA_HEAD = "0071_cricsheet_backfill"
DB_SCHEMA_LEVEL = 71

# --- Desktop client compatibility rules (explicit; never inferred) ---
# A desktop older than MIN_DESKTOP_VERSION must update before it may operate.
MIN_DESKTOP_VERSION = "1.0.0-beta.1"
# A desktop newer than this needs a newer server (None = no upper bound beyond the API contract).
MAX_DESKTOP_VERSION: str | None = None
# The oldest server a desktop of the current line is willing to talk to (advertised to clients).
MIN_SERVER_FOR_DESKTOP = "1.0.0-beta.1"


@dataclass(frozen=True)
class SemVer:
    major: int
    minor: int
    patch: int
    prerelease: tuple[Any, ...]  # empty tuple means a final release (which outranks any prerelease)

    def _key(self) -> tuple[Any, ...]:
        # A final release sorts after any prerelease of the same x.y.z (PEP 440 / semver spirit).
        return (self.major, self.minor, self.patch, 0 if not self.prerelease else -1, self.prerelease)


_SEMVER_RE = re.compile(r"^\s*v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.\-]+))?(?:\+[0-9A-Za-z.\-]+)?\s*$")


def parse_version(v: str) -> SemVer | None:
    """Parse a semantic version string (e.g. '1.2.0', '1.0.0-beta.1'); None if unparseable."""
    if not isinstance(v, str):
        return None
    m = _SEMVER_RE.match(v)
    if not m:
        return None
    major, minor, patch, pre = m.groups()
    pre_parts: tuple[Any, ...] = ()
    if pre:
        # Numeric identifiers compare numerically and rank below alphanumerics (semver §11).
        pre_parts = tuple(int(p) if p.isdigit() else p for p in pre.split("."))
    return SemVer(int(major), int(minor), int(patch), pre_parts)


def compare_versions(a: str, b: str) -> int:
    """Return -1 if a<b, 0 if equal/one-unparseable-equal, 1 if a>b. Unparseable sorts low."""
    pa, pb = parse_version(a), parse_version(b)
    if pa is None and pb is None:
        return 0
    if pa is None:
        return -1
    if pb is None:
        return 1
    ka, kb = pa._key(), pb._key()
    return -1 if ka < kb else (1 if ka > kb else 0)


def evaluate_compatibility(desktop_version: str | None, *, maintenance: bool = False) -> dict[str, Any]:
    """Decide whether a desktop client may operate against this server.

    Returns a dict with:
      status        — one of: ok | desktop_too_old | desktop_too_new | maintenance | unknown
      can_operate   — whether normal use is allowed right now
      required_action — update_desktop | update_server | wait | none
      message       — a short, user-facing explanation
    """
    if maintenance:
        return {"status": "maintenance", "can_operate": False, "required_action": "wait",
                "message": "The OneStats server is updating. Please wait a few minutes and try again."}
    if not desktop_version or parse_version(desktop_version) is None:
        return {"status": "unknown", "can_operate": True, "required_action": "none",
                "message": "Could not read the desktop version; proceeding."}
    if compare_versions(desktop_version, MIN_DESKTOP_VERSION) < 0:
        return {"status": "desktop_too_old", "can_operate": False, "required_action": "update_desktop",
                "message": f"This OneStats app ({desktop_version}) is older than the minimum "
                           f"supported version ({MIN_DESKTOP_VERSION}). Please update to continue."}
    if MAX_DESKTOP_VERSION is not None and compare_versions(desktop_version, MAX_DESKTOP_VERSION) > 0:
        return {"status": "desktop_too_new", "can_operate": False, "required_action": "update_server",
                "message": f"This OneStats app ({desktop_version}) is newer than this server supports. "
                           "Ask your administrator to update the OneStats server."}
    return {"status": "ok", "can_operate": True, "required_action": "none", "message": "Compatible."}
