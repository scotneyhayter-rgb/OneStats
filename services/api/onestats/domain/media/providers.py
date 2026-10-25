"""Media storage providers (Phase 11, Stages 11.1-11.4) — one interface, three implementations.

A ``MediaStorageProvider`` exposes put / get / exists / stat / delete against a provider-specific
**locator**, while OneStats tracks a storage-location-independent **stable media id** separately (the
media_asset row). Implementations:

* **InternalStorageProvider** (default) — OneStats-managed files under ``<media_root>/media/<ws>/``,
  workspace-partitioned, traversal-guarded; originals preserved byte-for-byte.
* **ExternalReferenceProvider** — the asset points at a file OneStats does NOT own (a URL/path). OneStats
  stores only the reference; it never fetches, modifies or deletes the external original.
* **OneVaultProvider** — optional. It **detects** at runtime whether a real OneVault API exists; until a
  verified API is confirmed it reports *unavailable* and refuses to fetch/store. No OneVault API is
  invented, and the separate OneVault application is never modified.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from onestats.core.config import Settings

PROVIDERS = ("internal", "onevault", "external")


class MediaStorageError(ValueError):
    pass


class ProviderUnavailable(RuntimeError):
    """A provider cannot service the request (e.g. OneVault has no verified API)."""


@runtime_checkable
class MediaStorageProvider(Protocol):
    name: str

    def put(self, settings: Settings, workspace_id: UUID, raw: bytes, content_type: str) -> dict[str, Any]: ...
    def get(self, settings: Settings, workspace_id: UUID, locator: str) -> bytes: ...
    def exists(self, settings: Settings, workspace_id: UUID, locator: str) -> bool: ...
    def delete(self, settings: Settings, workspace_id: UUID, locator: str) -> None: ...


# --- internal ------------------------------------------------------------------------------------
_EXT = {
    "image/png": "png", "image/jpeg": "jpg", "image/webp": "webp", "image/tiff": "tiff",
    "image/gif": "gif", "application/pdf": "pdf",
}


class InternalStorageProvider:
    name = "internal"

    def _dir(self, settings: Settings, workspace_id: UUID) -> Path:
        root = Path(settings.media_root).resolve()
        target = (root / "media" / str(workspace_id)).resolve()
        if root != target and root not in target.parents:
            raise MediaStorageError("unsafe_path")
        target.mkdir(parents=True, exist_ok=True)
        return target

    def _resolve(self, settings: Settings, workspace_id: UUID, locator: str) -> Path | None:
        base = os.path.basename(locator)
        if base != locator or base in ("", ".", ".."):
            return None
        path = self._dir(settings, workspace_id) / base
        return path if path.exists() else None

    def put(self, settings: Settings, workspace_id: UUID, raw: bytes, content_type: str) -> dict[str, Any]:
        import uuid as _uuid
        ext = _EXT.get((content_type or "").lower(), "bin")
        name = f"media-{_uuid.uuid4().hex}.{ext}"
        (self._dir(settings, workspace_id) / name).write_bytes(raw)   # original preserved unaltered
        return {"locator": name, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}

    def get(self, settings: Settings, workspace_id: UUID, locator: str) -> bytes:
        path = self._resolve(settings, workspace_id, locator)
        if path is None:
            raise MediaStorageError("not_found")
        return path.read_bytes()

    def exists(self, settings: Settings, workspace_id: UUID, locator: str) -> bool:
        return self._resolve(settings, workspace_id, locator) is not None

    def delete(self, settings: Settings, workspace_id: UUID, locator: str) -> None:
        path = self._resolve(settings, workspace_id, locator)
        if path is not None:
            path.unlink()

    def path(self, settings: Settings, workspace_id: UUID, locator: str) -> Path | None:
        return self._resolve(settings, workspace_id, locator)


# --- external reference --------------------------------------------------------------------------
class ExternalReferenceProvider:
    name = "external"

    def put(self, settings: Settings, workspace_id: UUID, raw: bytes, content_type: str) -> dict[str, Any]:
        # OneStats does not own external files; a reference is registered via the domain layer, not put here.
        raise MediaStorageError("external_reference_not_uploadable")

    def get(self, settings: Settings, workspace_id: UUID, locator: str) -> bytes:
        raise ProviderUnavailable("external reference is not fetched or stored by OneStats")

    def exists(self, settings: Settings, workspace_id: UUID, locator: str) -> bool:
        return bool(locator)   # the reference itself exists as metadata

    def delete(self, settings: Settings, workspace_id: UUID, locator: str) -> None:
        # never delete an original OneStats does not own
        return None


# --- OneVault (optional, capability-detected) ----------------------------------------------------
class OneVaultProvider:
    name = "onevault"

    def detect_capabilities(self, settings: Settings) -> dict[str, Any]:
        """Report what OneVault can do RIGHT NOW. No API is invented: unless a verified OneVault API is
        explicitly configured AND confirmed, this reports unavailable so OneVault options stay disabled."""
        api_url = getattr(settings, "onevault_api_url", None)
        verified = bool(getattr(settings, "onevault_verified", False))
        if api_url and verified:
            # A real, user-verified OneVault API would be probed here before being enabled.
            return {"available": True, "api_url": api_url, "note": "verified OneVault API configured"}
        return {
            "available": False,
            "reason": "No verified OneVault API configured. OneVault is optional; OneStats runs fully on "
                      "internal storage. Set a verified OneVault API to enable this provider.",
        }

    def _require(self, settings: Settings) -> None:
        if not self.detect_capabilities(settings)["available"]:
            raise ProviderUnavailable("OneVault integration is not available (no verified API).")

    def put(self, settings: Settings, workspace_id: UUID, raw: bytes, content_type: str) -> dict[str, Any]:
        self._require(settings)
        raise ProviderUnavailable("OneVault put not implemented (awaiting verified OneVault API).")

    def get(self, settings: Settings, workspace_id: UUID, locator: str) -> bytes:
        self._require(settings)
        raise ProviderUnavailable("OneVault get not implemented (awaiting verified OneVault API).")

    def exists(self, settings: Settings, workspace_id: UUID, locator: str) -> bool:
        return self.detect_capabilities(settings)["available"] and bool(locator)

    def delete(self, settings: Settings, workspace_id: UUID, locator: str) -> None:
        # OneStats never deletes originals held in OneVault.
        return None


_INTERNAL = InternalStorageProvider()
_EXTERNAL = ExternalReferenceProvider()
_ONEVAULT = OneVaultProvider()
_REGISTRY: dict[str, Any] = {"internal": _INTERNAL, "external": _EXTERNAL, "onevault": _ONEVAULT}


def get_provider(name: str):
    if name not in _REGISTRY:
        raise MediaStorageError("unknown_provider")
    return _REGISTRY[name]


def internal_provider() -> InternalStorageProvider:
    return _INTERNAL


def onevault_provider() -> OneVaultProvider:
    return _ONEVAULT


def describe_providers(settings: Settings) -> list[dict[str, Any]]:
    """Provider availability for the UI — internal always on; external on; OneVault capability-detected."""
    ov = _ONEVAULT.detect_capabilities(settings)
    return [
        {"name": "internal", "available": True, "default": True, "note": "OneStats-managed storage"},
        {"name": "external", "available": True, "default": False, "note": "Reference to a file OneStats does not own"},
        {"name": "onevault", "available": ov["available"], "default": False,
         "note": ov.get("note") or ov.get("reason")},
    ]
