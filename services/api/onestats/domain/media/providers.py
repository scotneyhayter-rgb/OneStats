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

PROVIDERS = ("internal", "onevault", "external", "s3")


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


# --- S3-compatible object storage (optional; cloud / shared deployments) ------------------------
class S3StorageProvider:
    """S3-compatible object storage — AWS S3, Cloudflare R2, MinIO, etc. — for cloud or shared-server
    deployments where media must not live on one PC's disk. boto3 is imported lazily and is an *optional*
    dependency: absent or unconfigured, every call raises :class:`ProviderUnavailable`, so the packaged
    desktop build (which never bundles boto3) is completely unaffected. The client is injectable for tests."""
    name = "s3"

    def __init__(self, client_factory: Any = None) -> None:
        self._client_factory = client_factory

    def _bucket(self, settings: Settings) -> str:
        b = getattr(settings, "s3_bucket", None)
        if not b:
            raise ProviderUnavailable("No S3 bucket configured (set ONESTATS_S3_BUCKET).")
        return b

    def _client(self, settings: Settings):
        if self._client_factory is not None:
            return self._client_factory()
        self._bucket(settings)
        try:
            import boto3
        except ImportError as exc:
            raise ProviderUnavailable("boto3 is not installed; `pip install boto3` to use S3 storage.") from exc
        return boto3.client(
            "s3",
            endpoint_url=(getattr(settings, "s3_endpoint_url", None) or None),
            region_name=(getattr(settings, "s3_region", None) or None),
            aws_access_key_id=(getattr(settings, "s3_access_key_id", None) or None),
            aws_secret_access_key=(getattr(settings, "s3_secret_access_key", None) or None),
        )

    def _key(self, settings: Settings, workspace_id: UUID, name: str) -> str:
        prefix = (getattr(settings, "s3_prefix", None) or "").strip("/")
        return "/".join(p for p in (prefix, "media", str(workspace_id), name) if p)

    def put(self, settings: Settings, workspace_id: UUID, raw: bytes, content_type: str) -> dict[str, Any]:
        import uuid as _uuid
        ext = _EXT.get((content_type or "").lower(), "bin")
        key = self._key(settings, workspace_id, f"media-{_uuid.uuid4().hex}.{ext}")
        self._client(settings).put_object(Bucket=self._bucket(settings), Key=key, Body=raw,
                                          ContentType=content_type or "application/octet-stream")
        return {"locator": key, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}

    def get(self, settings: Settings, workspace_id: UUID, locator: str) -> bytes:
        try:
            resp = self._client(settings).get_object(Bucket=self._bucket(settings), Key=locator)
            return resp["Body"].read()
        except ProviderUnavailable:
            raise
        except Exception as exc:  # map client/network/missing-key errors to a storage error
            raise MediaStorageError(f"s3_get_failed:{type(exc).__name__}") from exc

    def exists(self, settings: Settings, workspace_id: UUID, locator: str) -> bool:
        try:
            self._client(settings).head_object(Bucket=self._bucket(settings), Key=locator)
            return True
        except ProviderUnavailable:
            raise
        except Exception:  # noqa: BLE001 - a missing object or any error → treat as absent
            return False

    def delete(self, settings: Settings, workspace_id: UUID, locator: str) -> None:
        try:
            self._client(settings).delete_object(Bucket=self._bucket(settings), Key=locator)
        except ProviderUnavailable:
            raise
        except Exception:  # noqa: BLE001, S110 - best-effort delete; a failed cleanup must not break the flow
            pass


_INTERNAL = InternalStorageProvider()
_EXTERNAL = ExternalReferenceProvider()
_ONEVAULT = OneVaultProvider()
_S3 = S3StorageProvider()
_REGISTRY: dict[str, Any] = {"internal": _INTERNAL, "external": _EXTERNAL, "onevault": _ONEVAULT, "s3": _S3}


def get_provider(name: str):
    if name not in _REGISTRY:
        raise MediaStorageError("unknown_provider")
    return _REGISTRY[name]


def internal_provider() -> InternalStorageProvider:
    return _INTERNAL


def s3_provider() -> S3StorageProvider:
    return _S3


def onevault_provider() -> OneVaultProvider:
    return _ONEVAULT


def describe_providers(settings: Settings) -> list[dict[str, Any]]:
    """Provider availability for the UI — internal always on; external on; OneVault capability-detected."""
    ov = _ONEVAULT.detect_capabilities(settings)
    s3_on = bool(getattr(settings, "s3_bucket", None))
    return [
        {"name": "internal", "available": True, "default": True, "note": "OneStats-managed storage"},
        {"name": "external", "available": True, "default": False, "note": "Reference to a file OneStats does not own"},
        {"name": "onevault", "available": ov["available"], "default": False,
         "note": ov.get("note") or ov.get("reason")},
        {"name": "s3", "available": s3_on, "default": False,
         "note": "S3-compatible object storage" if s3_on else "Set ONESTATS_S3_BUCKET (and install boto3) to enable"},
    ]
