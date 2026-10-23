"""Unit tests: colour/contrast, image validation, and workspace-isolated logo storage."""

from __future__ import annotations

import io
import uuid

import pytest
from PIL import Image

from onestats.core import color, images
from onestats.core.config import Settings
from onestats.domain import logos


def _png(size=(12, 12), colour=(10, 20, 30, 255)) -> bytes:
    im = Image.new("RGBA", size, colour)
    b = io.BytesIO()
    im.save(b, format="PNG")
    return b.getvalue()


# --- colour / WCAG ---
def test_valid_hex():
    assert color.is_valid_hex("#fff") and color.is_valid_hex("#123abc")
    assert not color.is_valid_hex("123456") and not color.is_valid_hex("#12") and not color.is_valid_hex("blue")


def test_contrast_black_white_is_max():
    assert round(color.contrast_ratio("#000000", "#ffffff")) == 21


def test_best_foreground_and_resolve():
    assert color.best_foreground("#0b1120") == "#ffffff"
    assert color.best_foreground("#ffffff") == "#000000"
    r = color.resolve("#0b1120")
    assert r["foreground"] == "#ffffff" and r["meets_aa"] is True


# --- image validation ---
def test_validate_png_ok():
    ext, w, h = images.validate_image(_png(), "image/png", 1_000_000, 4096)
    assert ext == "png" and (w, h) == (12, 12)


def test_reject_non_image():
    with pytest.raises(images.ImageError, match="invalid_image"):
        images.validate_image(b"not an image", "image/png", 1_000_000, 4096)


def test_reject_type_mismatch():
    with pytest.raises(images.ImageError, match="type_mismatch"):
        images.validate_image(_png(), "image/jpeg", 1_000_000, 4096)  # PNG bytes, declared JPEG


def test_reject_oversize():
    with pytest.raises(images.ImageError, match="file_too_large"):
        images.validate_image(_png(), "image/png", 10, 4096)


def test_thumbnail_is_png():
    thumb = images.make_thumbnail(_png((400, 400)))
    assert images.validate_image(thumb, "image/png", 1_000_000, 4096)[0] == "png"


# --- logo storage (workspace-isolated) ---
def test_store_remove_logo(tmp_path):
    s = Settings(_env_file=None, media_root=str(tmp_path))
    ws = uuid.uuid4()
    stored = logos.store_logo(s, ws, _png(), "image/png")
    path = logos.logo_path(s, ws, stored["logo_ref"])
    assert path is not None and path.exists()
    assert (path.parent / f"{stored['logo_ref']}.thumb.png").exists()  # thumbnail
    assert str(ws) in str(path)  # workspace-isolated directory
    logos.remove_logo(s, ws, stored["logo_ref"])
    assert not path.exists()


def test_logo_ref_rejects_traversal(tmp_path):
    s = Settings(_env_file=None, media_root=str(tmp_path))
    ws = uuid.uuid4()
    with pytest.raises(ValueError, match="unsafe_ref"):
        logos.remove_logo(s, ws, "../../etc/passwd")
    assert logos.logo_path(s, ws, "../secret") is None


def test_two_workspaces_isolated(tmp_path):
    s = Settings(_env_file=None, media_root=str(tmp_path))
    a, b = uuid.uuid4(), uuid.uuid4()
    ra = logos.store_logo(s, a, _png(), "image/png")["logo_ref"]
    # workspace B cannot resolve workspace A's logo ref (different isolated dir)
    assert logos.logo_path(s, b, ra) is None
    assert logos.logo_path(s, a, ra) is not None
