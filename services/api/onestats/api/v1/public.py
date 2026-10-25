"""Public publishing edge (Phase 15, deliverable 29) — UNAUTHENTICATED, read-only.

Serves a published snapshot by slug with **no workspace context** and **no live engine** — it reads only
the stored snapshot (approved, publication-eligible data), so it works while the admin computer is offline
and never exposes the database or any admin surface. Unpublished/revoked slugs stop resolving. This same
edge is what a future central OneStats service would run; the static-export files (admin side) are the
alternative for existing website hosting.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import HTMLResponse

from onestats.api.deps import SettingsDep
from onestats.db.session import get_engine
from onestats.domain import publishing

router = APIRouter(prefix="/public", tags=["public"])

_SECURITY_HEADERS = {"X-Robots-Tag": "all", "Cache-Control": "public, max-age=300",
                     "Referrer-Policy": "no-referrer"}


def _fetch(settings, slug: str) -> dict[str, Any]:
    eng = get_engine(settings)
    if eng is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "unavailable")
    # a plain connection with NO workspace context — RLS exposes only published rows by slug
    with eng.connect() as conn:
        row = publishing.get_public(conn, slug)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    return row


@router.get("/r/{slug}.json")
def public_json(slug: str, settings: SettingsDep) -> Any:
    """Read-only JSON feed for a published report/profile (embedding + third-party consumption)."""
    row = _fetch(settings, slug)
    snap = row["snapshot"] if isinstance(row["snapshot"], dict) else {}
    return {"title": row["title"], "kind": row["kind"], "snapshot_at": row["snapshot_at"],
            "checksum": row["checksum"], **snap}


@router.get("/r/{slug}", response_class=HTMLResponse)
def public_html(slug: str, settings: SettingsDep) -> HTMLResponse:
    """Branded, self-contained, embeddable HTML page for a published report/profile."""
    row = _fetch(settings, slug)
    return HTMLResponse(content=row["snapshot_html"] or "", headers=_SECURITY_HEADERS)


@router.get("/p/{slug}", response_class=HTMLResponse)
def public_profile_html(slug: str, settings: SettingsDep) -> HTMLResponse:
    """Alias for a published public player profile (same slug space)."""
    row = _fetch(settings, slug)
    return HTMLResponse(content=row["snapshot_html"] or "", headers=_SECURITY_HEADERS)
