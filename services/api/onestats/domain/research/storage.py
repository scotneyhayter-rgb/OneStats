"""Research source-file storage (Phase 10, Stage 10.2/10.20).

A deliberately thin storage **abstraction** so source documents (newspaper scans, PDFs, photographs)
can later move to / be linked from OneVault (Phase 11) without re-coupling research records to one
location. Files live under ``<media_root>/research/<workspace_id>/`` with generated, non-guessable
names; the original is preserved byte-for-byte and its SHA-256 is recorded for integrity and
duplicate-source detection. The same security approach as logo/photo storage: basename-only, with a
resolved-path check to prevent traversal, so one workspace can never read or write another's files.
"""
from __future__ import annotations

import hashlib
import os
import uuid
from pathlib import Path
from uuid import UUID

from onestats.core.config import Settings

# Accepted source-document types and their canonical extensions (images + PDF). Handwritten/printed
# scorecards and photographs are uploaded as images or PDFs.
CONTENT_TYPES: dict[str, str] = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
    "image/tiff": "tiff",
    "image/gif": "gif",
    "application/pdf": "pdf",
}


class SourceFileError(ValueError):
    """A rejected source-file upload (type/size)."""


def _workspace_dir(settings: Settings, workspace_id: UUID) -> Path:
    root = Path(settings.media_root).resolve()
    target = (root / "research" / str(workspace_id)).resolve()
    if root != target and root not in target.parents:
        raise ValueError("unsafe_path")
    target.mkdir(parents=True, exist_ok=True)
    return target


def _safe_ref(file_ref: str) -> str:
    base = os.path.basename(file_ref)
    if base != file_ref or base in ("", ".", ".."):
        raise ValueError("unsafe_ref")
    return base


def store_source_file(settings: Settings, workspace_id: UUID, raw: bytes,
                      content_type: str) -> dict[str, object]:
    """Persist an uploaded source document unaltered; return its storage reference + integrity hash."""
    ext = CONTENT_TYPES.get((content_type or "").lower())
    if ext is None:
        raise SourceFileError("unsupported_source_type")
    if not raw:
        raise SourceFileError("empty_file")
    if len(raw) > settings.max_source_bytes:
        raise SourceFileError("file_too_large")
    directory = _workspace_dir(settings, workspace_id)
    name = f"src-{uuid.uuid4().hex}.{ext}"
    (directory / name).write_bytes(raw)
    return {
        "file_ref": name,
        "file_sha256": hashlib.sha256(raw).hexdigest(),
        "file_bytes": len(raw),
        "content_type": content_type.lower(),
    }


def source_file_path(settings: Settings, workspace_id: UUID, file_ref: str) -> Path | None:
    directory = _workspace_dir(settings, workspace_id)
    try:
        name = _safe_ref(file_ref)
    except ValueError:
        return None
    path = directory / name
    return path if path.exists() else None


def remove_source_file(settings: Settings, workspace_id: UUID, file_ref: str) -> None:
    path = source_file_path(settings, workspace_id, file_ref)
    if path is not None:
        path.unlink()
