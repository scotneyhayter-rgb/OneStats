"""Workspace-isolated logo storage (deliverable 9/20).

Logos live under ``<media_root>/branding/<workspace_id>/`` with generated, non-guessable
filenames. No caller-supplied path is ever trusted (basename-only; a resolved-path check
prevents traversal), so one workspace can never read or write another's media. Originals
are preserved; a PNG thumbnail is derived alongside.
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
    target = (root / "branding" / str(workspace_id)).resolve()
    # Ensure the resolved path stays within the media root (defence in depth).
    if root != target and root not in target.parents:
        raise ValueError("unsafe_path")
    target.mkdir(parents=True, exist_ok=True)
    return target


def _safe_ref(logo_ref: str) -> str:
    base = os.path.basename(logo_ref)
    if base != logo_ref or base in ("", ".", ".."):
        raise ValueError("unsafe_ref")
    return base


def store_logo(
    settings: Settings, workspace_id: UUID, raw: bytes, declared_type: str
) -> dict[str, object]:
    ext, width, height = images.validate_image(
        raw, declared_type, settings.max_logo_bytes, settings.max_logo_pixels
    )
    directory = _workspace_dir(settings, workspace_id)
    name = f"logo-{uuid.uuid4().hex}.{ext}"
    (directory / name).write_bytes(raw)  # preserve the original artwork unaltered
    (directory / f"{name}.thumb.png").write_bytes(images.make_thumbnail(raw))
    return {"logo_ref": name, "width": width, "height": height, "format": ext}


def remove_logo(settings: Settings, workspace_id: UUID, logo_ref: str) -> None:
    directory = _workspace_dir(settings, workspace_id)
    name = _safe_ref(logo_ref)
    for path in (directory / name, directory / f"{name}.thumb.png"):
        if path.exists():
            path.unlink()


def logo_path(settings: Settings, workspace_id: UUID, logo_ref: str) -> Path | None:
    directory = _workspace_dir(settings, workspace_id)
    try:
        name = _safe_ref(logo_ref)
    except ValueError:
        return None
    path = directory / name
    return path if path.exists() else None
