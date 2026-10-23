"""Colour validation and WCAG 2.2 contrast utilities (deliverable 9).

Used to validate workspace brand colours and to recommend accessible foreground colours
so text stays readable in both light and dark themes.
"""

from __future__ import annotations

import re

_HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")

WHITE = "#ffffff"
BLACK = "#000000"
AA_NORMAL = 4.5
AA_LARGE = 3.0


def is_valid_hex(value: str | None) -> bool:
    return bool(value) and bool(_HEX.match(value))


def _to_rgb(value: str) -> tuple[int, int, int]:
    h = value.lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _linear(channel: int) -> float:
    c = channel / 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(value: str) -> float:
    r, g, b = _to_rgb(value)
    return 0.2126 * _linear(r) + 0.7152 * _linear(g) + 0.0722 * _linear(b)


def contrast_ratio(a: str, b: str) -> float:
    la, lb = relative_luminance(a), relative_luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def best_foreground(background: str) -> str:
    """Return black or white — whichever contrasts better against the background."""
    return BLACK if contrast_ratio(background, BLACK) >= contrast_ratio(background, WHITE) else WHITE


def meets_aa(background: str, foreground: str, large_text: bool = False) -> bool:
    return contrast_ratio(background, foreground) >= (AA_LARGE if large_text else AA_NORMAL)


def resolve(background: str) -> dict[str, object]:
    """Resolve an accessible foreground for a background, with AA diagnostics."""
    fg = best_foreground(background)
    ratio = round(contrast_ratio(background, fg), 2)
    return {
        "background": background,
        "foreground": fg,
        "contrast_ratio": ratio,
        "meets_aa": ratio >= AA_NORMAL,
        "meets_aa_large": ratio >= AA_LARGE,
    }
