"""Publishing management endpoints (Phase 15, deliverable 29) — admin side, workspace-scoped.

Create/list publications, publish/unpublish/revoke, refresh snapshots, and download the static-export
files for existing website hosting. Public serving is the separate unauthenticated ``/public`` router.
"""
from __future__ import annotations

import io
import zipfile
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from onestats.api.deps import RequestContext, SettingsDep, require_permission
from onestats.db.session import get_engine
from onestats.db.workspace import workspace_transaction
from onestats.domain import publishing, publishing_github

router = APIRouter(prefix="/workspaces/{workspace_id}/publications", tags=["publishing"])

ManageCtx = Annotated[RequestContext, Depends(require_permission("workspace.manage"))]

_ERRORS = {
    "invalid_kind": status.HTTP_400_BAD_REQUEST,
    "unknown_report": status.HTTP_400_BAD_REQUEST,
    "person_required": status.HTTP_400_BAD_REQUEST,
    "unknown_organisation": status.HTTP_400_BAD_REQUEST,
    "invalid_status": status.HTTP_400_BAD_REQUEST,
    "invalid_base_url": status.HTTP_400_BAD_REQUEST,
    "invalid_repo": status.HTTP_400_BAD_REQUEST,
    "github_not_configured": status.HTTP_400_BAD_REQUEST,
    "publication_not_found": status.HTTP_404_NOT_FOUND,
}


def _engine(settings):
    eng = get_engine(settings)
    if eng is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database not configured")
    return eng


def _err(exc: ValueError) -> HTTPException:
    msg = str(exc)
    if msg.startswith("github_push_failed"):
        # an error from GitHub's API (bad token, repo gone, rate limit, …) — surface it as a bad gateway
        return HTTPException(status.HTTP_502_BAD_GATEWAY, msg)
    return HTTPException(_ERRORS.get(msg, status.HTTP_400_BAD_REQUEST), msg)


class PublishBody(BaseModel):
    kind: str = Field(pattern="^(report|player_profile)$")
    title: str = Field(min_length=1, max_length=200)
    report_id: str | None = None
    person_id: UUID | None = None
    filters: dict[str, Any] = Field(default_factory=dict)


class StatusBody(BaseModel):
    status: str = Field(pattern="^(published|unpublished|revoked)$")


class SettingsBody(BaseModel):
    public_base_url: str | None = None


class GithubBody(BaseModel):
    repo: str | None = None
    branch: str | None = None
    token: str | None = None  # only applied when explicitly present in the request body


def _public_urls(settings, base: str | None, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # The workspace's own hosting address (set in Website Publishing) wins; fall back to the server-level
    # default. `public_path` is the in-app preview route (served by this backend); `public_url` points at
    # the static files on the public host, matching the whole-site export layout (r/<slug>.html, p/...).
    host = base or settings.public_base_url
    for r in rows:
        folder = "p" if r["kind"] == "player_profile" else "r"
        r["public_path"] = f"/api/v1/public/{folder}/{r['slug']}"
        r["json_path"] = f"/api/v1/public/r/{r['slug']}.json"
        if host:
            root = host.rstrip("/")
            r["public_url"] = f"{root}/{folder}/{r['slug']}.html"
            r["json_url"] = f"{root}/{folder}/{r['slug']}.json"
        else:
            r["public_url"] = None
            r["json_url"] = None
    return rows


@router.get("")
def list_publications(workspace_id: UUID, settings: SettingsDep, ctx: ManageCtx) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        base = publishing.get_public_base_url(conn, workspace_id)
        return _public_urls(settings, base, publishing.list_publications(conn, workspace_id))


@router.get("/settings")
def get_settings_(workspace_id: UUID, settings: SettingsDep, ctx: ManageCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return {"public_base_url": publishing.get_public_base_url(conn, workspace_id)}


@router.put("/settings")
def set_settings_(workspace_id: UUID, body: SettingsBody, settings: SettingsDep, ctx: ManageCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            value = publishing.set_public_base_url(conn, workspace_id, str(ctx.user["id"]), body.public_base_url)
        except ValueError as exc:
            raise _err(exc) from exc
        return {"public_base_url": value}


@router.get("/site.zip")
def site_zip(workspace_id: UUID, settings: SettingsDep, ctx: ManageCtx) -> Response:
    """The entire published site as a downloadable .zip, laid out for a static host (GitHub Pages et al.).
    Regenerates all snapshots from current data + branding first, so the download is always current."""
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        files, _refresh = publishing.regenerate_and_export(conn, settings, workspace_id, str(ctx.user["id"]))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="onestats-public-site.zip"'},
    )


@router.get("/github")
def github_get(workspace_id: UUID, settings: SettingsDep, ctx: ManageCtx) -> dict[str, Any]:
    """The GitHub connection for display — the token is never returned, only whether one is stored."""
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return publishing_github.get_settings(conn, workspace_id)


@router.put("/github")
def github_set(workspace_id: UUID, body: GithubBody, settings: SettingsDep, ctx: ManageCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            # only touch the stored token when the client actually sent the field (so saving the repo
            # alone never wipes the secret, and the client need not round-trip it)
            return publishing_github.set_settings(
                conn, workspace_id, str(ctx.user["id"]), repo=body.repo, branch=body.branch,
                token=body.token, token_provided="token" in body.model_fields_set)
        except ValueError as exc:
            raise _err(exc) from exc


@router.post("/github/publish")
def github_publish(workspace_id: UUID, settings: SettingsDep, ctx: ManageCtx) -> dict[str, Any]:
    """Regenerate every published snapshot from current data + branding, then push the whole site to the
    configured GitHub repository as a single commit. Returns the commit, file count and refreshed/skipped."""
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return publishing_github.publish_to_github(conn, workspace_id, str(ctx.user["id"]), settings=settings)
        except ValueError as exc:
            raise _err(exc) from exc


@router.get("/github/pages-status")
def github_pages_status(workspace_id: UUID, settings: SettingsDep, ctx: ManageCtx) -> dict[str, Any]:
    """Best-effort GitHub Pages deploy status for the configured repo, so the UI can poll for a genuine
    'Live ✓' after a publish. Never errors — returns state 'unknown' when it cannot tell, so the client
    degrades to the time estimate."""
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return publishing_github.pages_build_status(conn, workspace_id)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_publication(workspace_id: UUID, body: PublishBody, settings: SettingsDep, ctx: ManageCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            row = publishing.create_publication(conn, settings, workspace_id, str(ctx.user["id"]),
                                                kind=body.kind, title=body.title, report_id=body.report_id,
                                                person_id=body.person_id, filters=body.filters)
        except ValueError as exc:
            raise _err(exc) from exc
        base = publishing.get_public_base_url(conn, workspace_id)
        return _public_urls(settings, base, [{k: (str(v) if isinstance(v, UUID) else v) for k, v in row.items()
                                              if k in ("id", "kind", "slug", "status", "title")}])[0]


@router.post("/refresh")
def refresh_all(workspace_id: UUID, settings: SettingsDep, ctx: ManageCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return publishing.refresh_workspace(conn, settings, workspace_id, str(ctx.user["id"]))


@router.post("/{pub_id}/refresh")
def refresh_one(workspace_id: UUID, pub_id: UUID, settings: SettingsDep, ctx: ManageCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            row = publishing.republish(conn, settings, workspace_id, str(ctx.user["id"]), pub_id)
        except ValueError as exc:
            raise _err(exc) from exc
        return {"id": str(row["id"]), "status": row["status"], "snapshot_at": row["snapshot_at"]}


@router.post("/{pub_id}/status")
def set_status(workspace_id: UUID, pub_id: UUID, body: StatusBody, settings: SettingsDep, ctx: ManageCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            row = publishing.set_status(conn, workspace_id, str(ctx.user["id"]), pub_id, body.status)
        except ValueError as exc:
            raise _err(exc) from exc
        return {"id": str(row["id"]), "status": row["status"]}


@router.delete("/{pub_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_publication(workspace_id: UUID, pub_id: UUID, settings: SettingsDep, ctx: ManageCtx) -> None:
    """Permanently remove a publication (unlike unpublish/revoke, which keep the record)."""
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            publishing.delete_publication(conn, workspace_id, str(ctx.user["id"]), pub_id)
        except ValueError as exc:
            raise _err(exc) from exc


@router.get("/{pub_id}/export")
def static_export(workspace_id: UUID, pub_id: UUID, settings: SettingsDep, ctx: ManageCtx) -> dict[str, Any]:
    """The self-contained files (JSON + HTML) to upload to existing website hosting."""
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            files = publishing.static_export(conn, workspace_id, pub_id)
        except ValueError as exc:
            raise _err(exc) from exc
        return {"files": files}
