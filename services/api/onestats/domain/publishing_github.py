"""One-click 'Publish to web' — push the published static site straight to a GitHub Pages repository.

This is the direct-upload alternative to the manual zip export. A workspace stores its GitHub connection
(``owner/name`` repo, branch, and a fine-grained personal access token with Contents write). Pressing
*Publish to GitHub* builds the same approved, branded whole-site export (:func:`publishing.site_export`)
and commits every file in **one commit** via GitHub's Git Data API (blobs → tree → commit → ref), so the
repo history stays clean and GitHub Pages redeploys automatically.

Security & integrity:

* The token lives **server-side only** and is never returned to the client (write-only). The public edge
  never reads it. It is used solely to push to the user's own repository, at the user's explicit request.
* Only approved, public, non-private snapshots are ever pushed — the database is never exposed.
* The push is a clean mirror: the commit's tree is exactly the exported files, so unpublished items stop
  being served. Use a repository dedicated to the published site (as the in-app guidance says).
"""
from __future__ import annotations

import re
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.core.config import Settings
from onestats.core.config import get_settings as _app_settings
from onestats.domain import audit, publishing

_GITHUB_API = "https://api.github.com"
_REPO_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*$")
_HEADERS = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "OneStats"}


def get_settings(conn: Connection, workspace_id: UUID) -> dict[str, Any]:
    """The GitHub connection for display — the token is never returned, only whether one is stored."""
    r = conn.execute(
        text("SELECT github_repo, github_branch, github_token FROM workspace WHERE id = :w"),
        {"w": workspace_id},
    ).mappings().first()
    if r is None:
        return {"repo": None, "branch": "main", "token_set": False}
    return {"repo": r["github_repo"], "branch": r["github_branch"] or "main",
            "token_set": bool(r["github_token"])}


def set_settings(conn: Connection, workspace_id: UUID, actor: str, *, repo: str | None,
                 branch: str | None, token: str | None = None, token_provided: bool = False) -> dict[str, Any]:
    """Store the GitHub connection. ``repo`` is ``owner/name``; ``branch`` defaults to ``main``.

    The token is only changed when ``token_provided`` is True: a non-empty value sets it, an empty string
    clears it, and leaving it out keeps the existing token (so saving the repo never wipes the token, and
    the client never has to round-trip the secret)."""
    repo_clean = (repo or "").strip() or None
    if repo_clean is not None and not _REPO_RE.match(repo_clean):
        raise ValueError("invalid_repo")
    branch_clean = (branch or "").strip() or "main"
    if token_provided:
        tok = (token or "").strip() or None
        conn.execute(
            text("UPDATE workspace SET github_repo = :r, github_branch = :b, github_token = :t WHERE id = :w"),
            {"r": repo_clean, "b": branch_clean, "t": tok, "w": workspace_id},
        )
    else:
        conn.execute(
            text("UPDATE workspace SET github_repo = :r, github_branch = :b WHERE id = :w"),
            {"r": repo_clean, "b": branch_clean, "w": workspace_id},
        )
    # audit the connection change WITHOUT the token value
    audit.write_audit(conn, workspace_id, actor, "publication.github_connect", entity="workspace",
                      entity_id=str(workspace_id),
                      after={"repo": repo_clean, "branch": branch_clean, "token_changed": token_provided})
    return get_settings(conn, workspace_id)


def _detail(resp: httpx.Response) -> str:
    try:
        msg = resp.json().get("message", "")
    except ValueError:
        msg = ""  # non-JSON body
    return f"github_push_failed: {resp.status_code} {msg}".strip()


def _ensure_pages(client: httpx.Client, owner: str, name: str, branch: str) -> str | None:
    """Best-effort: make sure GitHub Pages serves this branch at the site root and return its URL.
    Never raises — if the token can't manage Pages, the files are still pushed and the user can enable
    Pages by hand (the in-app steps)."""
    try:
        r = client.get(f"/repos/{owner}/{name}/pages")
        if r.status_code == 200:
            return r.json().get("html_url")
        if r.status_code == 404:
            c = client.post(f"/repos/{owner}/{name}/pages",
                            json={"source": {"branch": branch, "path": "/"}})
            if c.status_code in (201, 200):
                return c.json().get("html_url")
    except (httpx.HTTPError, ValueError):
        return None  # Pages management is optional — never fail the push over it
    return None


def publish_to_github(conn: Connection, workspace_id: UUID, actor: str,
                      *, settings: Settings | None = None,
                      transport: httpx.BaseTransport | None = None) -> dict[str, Any]:
    """Regenerate every published snapshot from CURRENT data + branding, then build the whole-site export
    and push it to the configured repo as a single commit via the Git Data API. Regenerating first makes a
    publish deterministic — it always ships current content and the current theme, never a stale stored
    snapshot. Returns the commit sha, file count, how many items were refreshed/skipped, and (best-effort)
    the live Pages URL. Raises ValueError with ``github_not_configured`` / ``invalid_repo`` /
    ``github_push_failed: …`` on failure."""
    settings = settings or _app_settings()
    s = conn.execute(
        text("SELECT github_repo, github_branch, github_token FROM workspace WHERE id = :w"),
        {"w": workspace_id},
    ).mappings().first()
    repo = (s["github_repo"] if s else None) or ""
    token = (s["github_token"] if s else None) or ""
    branch = (s["github_branch"] if s else None) or "main"
    if not repo or not token:
        raise ValueError("github_not_configured")
    if not _REPO_RE.match(repo):
        raise ValueError("invalid_repo")
    owner, name = repo.split("/", 1)

    # Regenerate ALL published snapshots from current data + branding BEFORE exporting, so the push is a
    # deterministic mirror of current content and theme (not whatever happened to be stored). One failing
    # item is reported in ``skipped``, never silently dropped and never aborting the push.
    files, refresh = publishing.regenerate_and_export(conn, settings, workspace_id, actor)
    headers = {**_HEADERS, "Authorization": f"Bearer {token}"}
    with httpx.Client(base_url=_GITHUB_API, headers=headers, transport=transport, timeout=120.0) as client:
        # Resolve the current branch tip (if the repo already has one). A brand-new empty repo has no ref
        # yet (404/409) — then we create the first commit with no parent and initialise the branch.
        ref = client.get(f"/repos/{owner}/{name}/git/ref/heads/{branch}")
        parents: list[str] = []
        base_sha: str | None = None
        if ref.status_code == 200:
            base_sha = ref.json()["object"]["sha"]
            parents = [base_sha]
        elif ref.status_code not in (404, 409):
            raise ValueError(_detail(ref))

        # Build the whole tree in ONE request: each file's text goes inline as `content`, so GitHub creates
        # the blobs server-side — no per-file blob POST (far fewer round trips for a large site). No
        # base_tree, so the commit is an exact mirror of the export (removed/unpublished items disappear).
        tree = [{"path": path, "mode": "100644", "type": "blob", "content": content}
                for path, content in files.items()]
        tree_resp = client.post(f"/repos/{owner}/{name}/git/trees", json={"tree": tree})
        if tree_resp.status_code not in (200, 201):
            raise ValueError(_detail(tree_resp))
        tree_sha = tree_resp.json()["sha"]

        commit_resp = client.post(
            f"/repos/{owner}/{name}/git/commits",
            json={"message": f"Publish OneStats site ({len(files)} files)", "tree": tree_sha, "parents": parents})
        if commit_resp.status_code not in (200, 201):
            raise ValueError(_detail(commit_resp))
        commit_sha = commit_resp.json()["sha"]

        if base_sha is not None:
            upd = client.patch(f"/repos/{owner}/{name}/git/refs/heads/{branch}",
                               json={"sha": commit_sha, "force": True})
        else:
            upd = client.post(f"/repos/{owner}/{name}/git/refs",
                              json={"ref": f"refs/heads/{branch}", "sha": commit_sha})
        if upd.status_code not in (200, 201):
            raise ValueError(_detail(upd))

        pages_url = _ensure_pages(client, owner, name, branch)

    # Populate the public site address automatically if the club hasn't set one yet, so each report's
    # copyable public link appears without a second manual step.
    if pages_url and not publishing.get_public_base_url(conn, workspace_id):
        try:
            publishing.set_public_base_url(conn, workspace_id, actor, pages_url)
        except ValueError:
            pass

    audit.write_audit(conn, workspace_id, actor, "publication.github_publish", entity="workspace",
                      entity_id=str(workspace_id),
                      after={"repo": repo, "branch": branch, "files": len(files), "commit": commit_sha,
                             "refreshed": refresh["refreshed"], "skipped": len(refresh["skipped"])})
    return {"committed": True, "commit": commit_sha, "files": len(files), "repo": repo,
            "branch": branch, "pages_url": pages_url,
            "refreshed": refresh["refreshed"], "skipped": refresh["skipped"]}


def pages_build_status(conn: Connection, workspace_id: UUID,
                       *, transport: httpx.BaseTransport | None = None) -> dict[str, Any]:
    """Best-effort GitHub Pages deploy status for the configured repo, so the UI can resolve a genuine
    'Live ✓' after a publish by polling. **Never raises**: anything unexpected (not configured, Pages not
    enabled, API/network error, odd payload) returns ``state: 'unknown'`` so the caller degrades to the
    honest time-estimate message rather than hanging or showing a false failure.

    ``state`` is one of ``building`` / ``built`` / ``errored`` / ``unknown`` and ``commit`` is the sha the
    latest build deployed (the caller compares it to the commit it just pushed). NOTE: ``built`` means the
    deploy succeeded at the origin — a CDN/browser-cache tail of a few minutes can remain, so the UI must
    not claim every viewer sees it instantly."""
    s = conn.execute(text("SELECT github_repo, github_token FROM workspace WHERE id = :w"),
                     {"w": workspace_id}).mappings().first()
    repo = (s["github_repo"] if s else None) or ""
    token = (s["github_token"] if s else None) or ""
    if not repo or not token or not _REPO_RE.match(repo):
        return {"state": "unknown", "reason": "github_not_configured"}
    owner, name = repo.split("/", 1)
    headers = {**_HEADERS, "Authorization": f"Bearer {token}"}
    try:
        with httpx.Client(base_url=_GITHUB_API, headers=headers, transport=transport, timeout=15.0) as client:
            r = client.get(f"/repos/{owner}/{name}/pages/builds/latest")
            if r.status_code == 404:
                return {"state": "unknown", "reason": "pages_not_enabled"}
            if r.status_code != 200:
                return {"state": "unknown", "reason": f"status_{r.status_code}"}
            data = r.json()
    except (httpx.HTTPError, ValueError):
        return {"state": "unknown", "reason": "unreachable"}
    raw = str(data.get("status") or "").lower()
    state = {"built": "built", "building": "building", "queued": "building",
             "errored": "errored"}.get(raw, "unknown")
    return {"state": state, "commit": data.get("commit") or None}
