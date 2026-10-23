"""Person-photo storage unit tests (filesystem; no DB).

Verifies the Phase 5 photo storage reuses the Phase 3 image pipeline safely: validates real
image bytes, stores under a workspace-isolated directory with a non-guessable name + thumbnail,
rejects spoofed/non-image bytes and path traversal, and removes files cleanly. Uses a temporary
media root so nothing persists.
"""

from __future__ import annotations

import io
import uuid

import pytest
from PIL import Image

from onestats.core import images
from onestats.core.config import Settings
from onestats.domain import photos


def _png_bytes(size=(32, 32)) -> bytes:
    im = Image.new("RGB", size, (10, 20, 30))
    out = io.BytesIO()
    im.save(out, format="PNG")
    return out.getvalue()


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(env="test", db_password=None, media_root=str(tmp_path), _env_file=None)


def test_store_and_fetch_and_remove(settings):
    wid = uuid.uuid4()
    stored = photos.store_photo(settings, wid, _png_bytes(), "image/png")
    assert stored["format"] == "png" and stored["width"] == 32
    key = str(stored["media_key"])
    assert key.startswith("photo-") and key.endswith(".png")
    path = photos.photo_path(settings, wid, key)
    assert path is not None and path.exists()
    # a thumbnail was derived alongside
    assert (path.parent / f"{key}.thumb.png").exists()
    photos.remove_photo(settings, wid, key)
    assert photos.photo_path(settings, wid, key) is None


def test_rejects_non_image(settings):
    with pytest.raises(images.ImageError):
        photos.store_photo(settings, uuid.uuid4(), b"not an image", "image/png")


def test_workspace_isolation_of_paths(settings):
    wa, wb = uuid.uuid4(), uuid.uuid4()
    stored = photos.store_photo(settings, wa, _png_bytes(), "image/png")
    key = str(stored["media_key"])
    # the same key is not visible under a different workspace directory
    assert photos.photo_path(settings, wa, key) is not None
    assert photos.photo_path(settings, wb, key) is None


def test_path_traversal_ref_rejected(settings):
    wid = uuid.uuid4()
    assert photos.photo_path(settings, wid, "../secret.png") is None
    assert photos.photo_path(settings, wid, "a/b.png") is None
