"""Safe image validation and thumbnailing for logo uploads (deliverable 9/20).

Defends against type spoofing (the real format is verified with Pillow, not trusted from
the declared content-type), oversized files, and decompression bombs (pixel limit). SVG is
intentionally not accepted here (script-injection risk). Originals are preserved by the
caller; this module only validates and derives a thumbnail.
"""

from __future__ import annotations

import io

from PIL import Image, UnidentifiedImageError

# declared content-type -> canonical extension
ALLOWED_TYPES = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}
_FORMAT_EXT = {"png": "png", "jpeg": "jpg", "webp": "webp"}


class ImageError(ValueError):
    pass


def validate_image(
    raw: bytes, declared_type: str, max_bytes: int, max_pixels: int
) -> tuple[str, int, int]:
    """Return (extension, width, height) if the bytes are a safe, supported image."""
    if len(raw) == 0:
        raise ImageError("empty_file")
    if len(raw) > max_bytes:
        raise ImageError("file_too_large")
    if declared_type not in ALLOWED_TYPES:
        raise ImageError("unsupported_type")
    Image.MAX_IMAGE_PIXELS = max_pixels * max_pixels  # decompression-bomb guard
    try:
        with Image.open(io.BytesIO(raw)) as im:
            fmt = (im.format or "").lower()
            width, height = im.size
            im.verify()  # detect truncated/corrupt files
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ImageError("invalid_image") from exc
    if fmt not in _FORMAT_EXT:
        raise ImageError("unsupported_type")
    ext = _FORMAT_EXT[fmt]
    if ALLOWED_TYPES[declared_type] != ext:
        raise ImageError("type_mismatch")  # declared type must match actual bytes
    if width > max_pixels or height > max_pixels:
        raise ImageError("dimensions_too_large")
    return ext, width, height


def make_thumbnail(raw: bytes, size: tuple[int, int] = (128, 128)) -> bytes:
    with Image.open(io.BytesIO(raw)) as im:
        if im.mode in ("P", "LA"):
            im = im.convert("RGBA")
        im.thumbnail(size)
        out = io.BytesIO()
        im.save(out, format="PNG")
        return out.getvalue()
