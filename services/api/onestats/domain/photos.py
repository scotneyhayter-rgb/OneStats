"""Workspace-isolated person-photo storage (Phase 5, Stage 4).

Reuses the Phase 3 image pipeline (``onestats.core.images`` validation + thumbnailing) and the
same security approach as logo storage: files live under ``<media_root>/people/<workspace_id>/``
with generated, non-guessable names, no caller-supplied path is trusted, and a resolved-path check
prevents traversal. Originals are preserved; a PNG thumbnail is derived alongside. This adds no new
security or storage machinery — only a person-photo location.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from uuid import UUID

from onestats.core import images
from onestats.core.config import Settings


def _workspace_dir(settings: Settings, workspace_id: UUID) -> Path:
    root = Path(settings.media_root).resolve()
    target = (root / "people" / str(workspace_id)).resolve()
    if root != target and root not in target.parents:
        raise ValueError("unsafe_path")
    target.mkdir(parents=True, exist_ok=True)
    return target


def _safe_ref(media_key: str) -> str:
    base = os.path.basename(media_key)
    if base != media_key or base in ("", ".", ".."):
        raise ValueError("unsafe_ref")
    return base


def store_photo(settings: Settings, workspace_id: UUID, raw: bytes, declared_type: str) -> dict[str, object]:
    ext, width, height = images.validate_image(
        raw, declared_type, settings.max_logo_bytes, settings.max_logo_pixels
    )
    directory = _workspace_dir(settings, workspace_id)
    name = f"photo-{uuid.uuid4().hex}.{ext}"
    (directory / name).write_bytes(raw)
    (directory / f"{name}.thumb.png").write_bytes(images.make_thumbnail(raw))
    return {"media_key": name, "width": width, "height": height, "format": ext}


def remove_photo(settings: Settings, workspace_id: UUID, media_key: str) -> None:
    directory = _workspace_dir(settings, workspace_id)
    name = _safe_ref(media_key)
    for path in (directory / name, directory / f"{name}.thumb.png"):
        if path.exists():
            path.unlink()


def photo_path(settings: Settings, workspace_id: UUID, media_key: str) -> Path | None:
    directory = _workspace_dir(settings, workspace_id)
    try:
        name = _safe_ref(media_key)
    except ValueError:
        return None
    path = directory / name
    return path if path.exists() else None
