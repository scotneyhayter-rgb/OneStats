"""Mobile upload — QR-paired, short-lived, scoped upload sessions (deliverable 20a).

A desktop user with ``media.manage`` starts a pairing session; a phone on the LAN uses the returned
single-use/short-lived **token** to upload media. Only the token's SHA-256 hash is stored (never the token
itself), sessions are time-limited and revocable, and every action is audited. Uploaded files are
type-verified (content sniff, not just the declared type) and size-limited, stored as preserved originals
via the media archive, and left **unassigned** so they enter the media review queue — nothing is
auto-published, and any extracted statistics still require human verification before official records.

Workspace isolation: ``upload_session`` has FORCE RLS; every call runs inside the workspace transaction, so
a session and its uploads belong only to the pairing user's workspace.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.core import security
from onestats.core.config import Settings
from onestats.domain import audit
from onestats.domain.media import assets

# accepted upload types, verified by content (magic bytes), not the declared content-type alone.
_PDF_MAGIC = b"%PDF-"
_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}
DEFAULT_TTL_MINUTES = 30
MAX_TTL_MINUTES = 240

_COLS = ("id, workspace_id, created_by, scope, status, upload_count, expires_at, created_at, "
         "last_used_at, revoked_at")


def _public(row: dict[str, Any]) -> dict[str, Any]:
    """A session row WITHOUT the token (there is no token column; this also normalises types)."""
    return {"id": str(row["id"]), "status": row["status"], "scope": row["scope"] or {},
            "upload_count": row["upload_count"],
            "expires_at": row["expires_at"].isoformat() if row["expires_at"] else None,
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "last_used_at": row["last_used_at"].isoformat() if row["last_used_at"] else None,
            "active": _is_active(row)}


def _is_active(row: dict[str, Any]) -> bool:
    return row["status"] == "active" and row["expires_at"] is not None and \
        row["expires_at"] > datetime.now(UTC)


def create_session(conn: Connection, workspace_id: UUID, actor: str, *,
                   ttl_minutes: int = DEFAULT_TTL_MINUTES, scope: dict[str, Any] | None = None) -> dict[str, Any]:
    """Start a pairing session. Returns the session plus the **raw token once** (never stored or shown
    again) for encoding into the QR/pairing URL."""
    ttl = max(1, min(int(ttl_minutes), MAX_TTL_MINUTES))
    token = security.generate_token()
    expires = datetime.now(UTC) + timedelta(minutes=ttl)
    import json
    sid = conn.execute(
        text("INSERT INTO upload_session(workspace_id, token_hash, created_by, scope, expires_at) "
             "VALUES (:w, :h, :a, CAST(:s AS jsonb), :e) RETURNING id"),
        {"w": workspace_id, "h": security.hash_token(token), "a": actor,
         "s": json.dumps(scope or {}), "e": expires},
    ).scalar_one()
    audit.write_audit(conn, workspace_id, actor, "mobile_upload.session.create",
                      entity="upload_session", entity_id=str(sid))
    row = _get(conn, workspace_id, sid)
    out = _public(row)
    out["token"] = token                                  # returned once, to the pairing desktop only
    return out


def _get(conn: Connection, workspace_id: UUID, session_id: UUID) -> dict[str, Any] | None:
    r = conn.execute(text(f"SELECT {_COLS} FROM upload_session WHERE id = :id AND workspace_id = :w"),
                     {"id": session_id, "w": workspace_id}).mappings().first()
    return dict(r) if r else None


def list_sessions(conn: Connection, workspace_id: UUID) -> list[dict[str, Any]]:
    rows = conn.execute(text(f"SELECT {_COLS} FROM upload_session WHERE workspace_id = :w "
                             "ORDER BY created_at DESC LIMIT 50"), {"w": workspace_id}).mappings().all()
    return [_public(dict(r)) for r in rows]


def revoke_session(conn: Connection, workspace_id: UUID, actor: str, session_id: UUID) -> dict[str, Any]:
    row = _get(conn, workspace_id, session_id)
    if row is None:
        raise ValueError("session_not_found")
    conn.execute(text("UPDATE upload_session SET status = 'revoked', revoked_at = now() "
                      "WHERE id = :id AND workspace_id = :w"), {"id": session_id, "w": workspace_id})
    audit.write_audit(conn, workspace_id, actor, "mobile_upload.session.revoke",
                      entity="upload_session", entity_id=str(session_id))
    return _public(_get(conn, workspace_id, session_id))


def resolve_token(conn: Connection, workspace_id: UUID, session_id: UUID, token: str) -> dict[str, Any] | None:
    """Return the session iff the token matches and the session is active and unexpired. The workspace is
    taken from the paired URL (so RLS scopes the lookup); the token proves the pairing."""
    if not token:
        return None
    row = conn.execute(
        text(f"SELECT {_COLS}, token_hash FROM upload_session WHERE id = :id AND workspace_id = :w"),
        {"id": session_id, "w": workspace_id}).mappings().first()
    if row is None:
        return None
    if not security.tokens_equal(row["token_hash"], security.hash_token(token)):
        return None
    row = dict(row)
    if not _is_active(row):
        return None
    row.pop("token_hash", None)                           # never carry the hash beyond verification
    return row


def _verify_type(raw: bytes, declared: str) -> tuple[str, str]:
    """Verify the file by content and return (content_type, kind). Rejects anything not an allowed image
    or a PDF. Images are validated with Pillow (real format, not the declared type); PDFs by magic bytes."""
    if raw[:5] == _PDF_MAGIC:
        return "application/pdf", "document"
    # treat everything else as a candidate image and verify the bytes really are a supported image
    from onestats.core import images
    try:
        ext, _, _ = images.validate_image(raw, declared if declared in _IMAGE_TYPES else "image/jpeg",
                                           max_bytes=10 ** 9, max_pixels=20000)
    except images.ImageError:
        # the declared type may be wrong; try the other supported image types before rejecting
        for t in _IMAGE_TYPES:
            try:
                images.validate_image(raw, t, max_bytes=10 ** 9, max_pixels=20000)
                return t, "photo"
            except images.ImageError:
                continue
        raise ValueError("unsupported_file_type") from None
    ct = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp"}[ext]
    return ct, "photo"


def accept_upload(conn: Connection, settings: Settings, workspace_id: UUID, session: dict[str, Any], *,
                  raw: bytes, content_type: str | None, filename: str | None) -> dict[str, Any]:
    """Verify and store one uploaded file as a preserved original, left UNASSIGNED for the media review
    queue. Attribution is the pairing user; the upload is audited. Never auto-published."""
    if not raw:
        raise ValueError("empty_file")
    if len(raw) > settings.max_media_bytes:
        raise ValueError("file_too_large")
    ct, kind = _verify_type(raw, (content_type or "").lower())
    actor = session.get("created_by") or "mobile-upload"
    asset = assets.create_internal_asset(
        conn, settings, workspace_id, str(actor), raw=raw, content_type=ct, original_filename=filename,
        kind=kind, source_provenance="mobile_upload", visibility="private", sensitive=False)
    conn.execute(text("UPDATE upload_session SET upload_count = upload_count + 1, last_used_at = now() "
                      "WHERE id = :id AND workspace_id = :w"), {"id": session["id"], "w": workspace_id})
    audit.write_audit(conn, workspace_id, str(actor), "mobile_upload.file.received",
                      entity="media_asset", entity_id=str(asset["id"]),
                      after={"session": str(session["id"]), "kind": kind})
    return {"asset_id": str(asset["id"]), "kind": kind, "content_type": ct,
            "duplicate_of": asset.get("duplicate_of"), "status": "received_for_review"}
