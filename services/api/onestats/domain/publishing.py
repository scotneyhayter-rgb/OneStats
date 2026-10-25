"""Website publishing (Phase 15, deliverable 29) — hosting-neutral.

Publishing a report or a public player profile creates a ``publication`` with a permanent unguessable
slug and a durable **snapshot** (rendered data + self-contained HTML + checksum + branding). Public access
reads the snapshot only — it never touches the live engine or the admin database, so it works while the
Windows computer is offline and serves the **last successfully published approved snapshot**.

The same snapshot feeds either (a) **static export** — files uploaded to existing website hosting (the RMCC
site's External URL field) — or (b) a future **central OneStats publishing service**. Nothing commits to
either approach. Only approved, publication-eligible data is snapshotted (no DOB/junior/private), so public
exposure is intended. Numbers always come from the one deterministic engine.
"""
from __future__ import annotations

import hashlib
import json
import secrets
from datetime import UTC, datetime
from html import escape
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.core.config import Settings
from onestats.domain import audit, branding, profiles
from onestats.domain.records import player_profile
from onestats.reports import catalogue

_COLS = ("id, workspace_id, kind, report_id, person_id, title, filters, slug, status, stale, "
         "snapshot, snapshot_html, checksum, snapshot_at, created_by, created_at, updated_at")


def _slug() -> str:
    return secrets.token_urlsafe(12)


def _branding(conn: Connection, workspace_id: UUID) -> dict[str, Any]:
    ws = conn.execute(text("SELECT name FROM workspace WHERE id = :w"), {"w": workspace_id}).mappings().first()
    b = branding.get_branding(conn, workspace_id) or {}
    colours = (b.get("colours") or {}) if isinstance(b, dict) else {}
    return {"club": (ws or {}).get("name") or "OneStats", "primary": colours.get("primary") or "#0b5e3b"}


def _filters(workspace_id: UUID, saved: dict[str, Any]) -> dict[str, Any]:
    f: dict[str, Any] = {"workspace_id": workspace_id}
    for k in ("season_id", "grade_id", "competition_id", "team_id", "split", "venue", "format"):
        if saved.get(k):
            f[k] = saved[k]
    return f


def _report_snapshot(conn: Connection, workspace_id: UUID, report_id: str, saved_filters: dict[str, Any],
                     brand: dict[str, Any]) -> dict[str, Any]:
    data = catalogue.report_rows(conn, workspace_id, report_id, _filters(workspace_id, saved_filters))
    entry = catalogue.CAT_BY_ID.get(report_id)
    quals = [n for n in ((entry.qualification if entry else None), (entry.limitations if entry else None)) if n]
    quals.append("Official statistics from approved scorecards only; unknown values are never treated as zero.")
    return {"kind": "report", "report_id": report_id, "report_name": data["title"],
            "columns": data["columns"], "rows": data["rows"], "qualifications": quals, "branding": brand}


def _profile_snapshot(conn: Connection, workspace_id: UUID, person_id: UUID, brand: dict[str, Any]) -> dict[str, Any]:
    # public career view strips internal / non-public / DOB / junior data (deliverable 12a/29.4a)
    view = profiles.career_view(conn, person_id, public=True) or {}
    prof = player_profile.full_profile(conn, workspace_id, person_id)
    person = view.get("person") or {}
    return {"kind": "player_profile", "person_name": person.get("display_name") or "Player",
            "career": prof["career"], "seasons": prof["seasons"], "records": prof["records"],
            "grand_finals": prof.get("grand_finals"),
            "honours": [{"title": h.get("title"), "category": h.get("award_category") or h.get("honour_type"),
                         "season": h.get("awarded_season")} for h in prof["honours"]],
            "branding": brand,
            "qualifications": [("Public profile — approved statistics only; personal contact details and "
                                "dates of birth are never published.")]}


def _render_html(snap: dict[str, Any], title: str, public_base: str, slug: str) -> str:
    brand = snap.get("branding") or {}
    primary = escape(str(brand.get("primary") or "#0b5e3b"))
    club = escape(str(brand.get("club") or "OneStats"))
    gen = datetime.now(UTC).strftime("%d %b %Y")
    body = []
    if snap["kind"] == "report":
        cols, rows = snap["columns"], snap["rows"]
        head = "".join(f"<th style='text-align:{'right' if c['align'] == 'right' else 'left'}'>{escape(c['label'])}</th>" for c in cols)
        trs = []
        for r in rows:
            tds = []
            for c in cols:
                v = r.get(c["key"])
                s = "—" if v is None else (f"{v:.{c['decimals']}f}" if c["decimals"] is not None and isinstance(v, (int, float)) else ("Yes" if v is True else "No" if v is False else escape(str(v))))
                tds.append(f"<td style='text-align:{'right' if c['align'] == 'right' else 'left'}'>{s}</td>")
            trs.append("<tr>" + "".join(tds) + "</tr>")
        body.append(f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(trs)}</tbody></table>")
        if not rows:
            body.append("<p class='muted'>No published data for this report yet.</p>")
    else:
        c = snap["career"]
        bat, bowl = c.get("batting", {}), c.get("bowling", {})
        body.append(f"<h2>{escape(snap['person_name'])}</h2>")
        body.append("<div class='cards'>"
                    + f"<div class='card'><span>Matches</span><b>{c.get('matches', 0)}</b></div>"
                    + f"<div class='card'><span>Runs</span><b>{bat.get('runs', 0)}</b></div>"
                    + f"<div class='card'><span>Bat avg</span><b>{bat.get('average') if bat.get('average') is not None else '—'}</b></div>"
                    + f"<div class='card'><span>Wickets</span><b>{bowl.get('wickets', 0)}</b></div>"
                    + "</div>")
    for q in snap.get("qualifications", []):
        body.append(f"<p class='muted'>{escape(q)}</p>")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(title)} — {club}</title>
<style>
:root{{--brand:{primary}}}
body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0;color:#17201c;background:#fff}}
header{{border-bottom:3px solid var(--brand);padding:12px 20px}}
header b{{color:var(--brand)}}
main{{padding:16px 20px;max-width:1000px;margin:0 auto}}
h1{{color:var(--brand);font-size:20px;margin:.2em 0}} h2{{color:var(--brand)}}
table{{border-collapse:collapse;width:100%;font-size:14px}}
th{{background:var(--brand);color:#fff;padding:6px 8px}} td{{padding:5px 8px;border-bottom:1px solid #e5eae7}}
tr:nth-child(even) td{{background:#f3f6f4}}
.cards{{display:flex;gap:10px;flex-wrap:wrap;margin:10px 0}}
.card{{border:1px solid #e5eae7;border-radius:8px;padding:8px 14px}} .card span{{display:block;font-size:12px;color:#5b665f}} .card b{{font-size:20px}}
.muted{{color:#5b665f;font-size:12px}} footer{{color:#8a938d;font-size:11px;padding:10px 20px;border-top:1px solid #e5eae7}}
</style></head><body>
<header><b>{club}</b></header>
<main><h1>{escape(title)}</h1>{''.join(body)}</main>
<footer>Published by OneStats · {gen}{(' · ' + escape(public_base) + '/r/' + escape(slug)) if public_base else ''}</footer>
</body></html>"""


def _snapshot(conn: Connection, settings: Settings, workspace_id: UUID, row: dict[str, Any]) -> dict[str, Any]:
    brand = _branding(conn, workspace_id)
    if row["kind"] == "report":
        snap = _report_snapshot(conn, workspace_id, row["report_id"], row.get("filters") or {}, brand)
    else:
        snap = _profile_snapshot(conn, workspace_id, row["person_id"], brand)
    snap["title"] = row["title"]
    snap["generated_at"] = datetime.now(UTC).isoformat()
    html = _render_html(snap, row["title"], settings.public_base_url or "", row["slug"])
    checksum = hashlib.sha256(json.dumps(snap, sort_keys=True, default=str).encode()).hexdigest()
    return {"snapshot": snap, "html": html, "checksum": checksum}


def _row(conn: Connection, workspace_id: UUID, pub_id: UUID) -> dict[str, Any] | None:
    r = conn.execute(text(f"SELECT {_COLS} FROM publication WHERE id = :id AND workspace_id = :w"),
                     {"id": pub_id, "w": workspace_id}).mappings().first()
    return dict(r) if r else None


def create_publication(conn: Connection, settings: Settings, workspace_id: UUID, actor: str, *, kind: str,
                       title: str, report_id: str | None = None, person_id: UUID | None = None,
                       filters: dict[str, Any] | None = None) -> dict[str, Any]:
    if kind not in ("report", "player_profile"):
        raise ValueError("invalid_kind")
    if kind == "report" and (not report_id or report_id not in catalogue.CAT_BY_ID):
        raise ValueError("unknown_report")
    if kind == "player_profile" and not person_id:
        raise ValueError("person_required")
    slug = _slug()
    pub_id = conn.execute(
        text("INSERT INTO publication(workspace_id, kind, report_id, person_id, title, filters, slug, status, created_by) "
             "VALUES (:w,:k,:rid,:pid,:t,CAST(:f AS jsonb),:s,'published',:a) RETURNING id"),
        {"w": workspace_id, "k": kind, "rid": report_id, "pid": person_id, "t": title,
         "f": json.dumps(filters or {}), "s": slug, "a": actor},
    ).scalar_one()
    _store_snapshot(conn, settings, workspace_id, pub_id)
    audit.write_audit(conn, workspace_id, actor, "publication.create", entity="publication", entity_id=str(pub_id))
    return _row(conn, workspace_id, pub_id)


def _store_snapshot(conn: Connection, settings: Settings, workspace_id: UUID, pub_id: UUID) -> None:
    row = _row(conn, workspace_id, pub_id)
    if row is None:
        raise ValueError("publication_not_found")
    s = _snapshot(conn, settings, workspace_id, row)
    conn.execute(
        text("UPDATE publication SET snapshot = CAST(:snap AS jsonb), snapshot_html = :html, checksum = :ck, "
             "snapshot_at = now(), stale = false, updated_at = now() WHERE id = :id AND workspace_id = :w"),
        {"snap": json.dumps(s["snapshot"], default=str), "html": s["html"], "ck": s["checksum"],
         "id": pub_id, "w": workspace_id},
    )


def set_status(conn: Connection, workspace_id: UUID, actor: str, pub_id: UUID, status: str) -> dict[str, Any]:
    if status not in ("published", "unpublished", "revoked"):
        raise ValueError("invalid_status")
    if _row(conn, workspace_id, pub_id) is None:
        raise ValueError("publication_not_found")
    conn.execute(text("UPDATE publication SET status = :s, updated_at = now() WHERE id = :id AND workspace_id = :w"),
                 {"s": status, "id": pub_id, "w": workspace_id})
    audit.write_audit(conn, workspace_id, actor, f"publication.{status}", entity="publication", entity_id=str(pub_id))
    return _row(conn, workspace_id, pub_id)


def republish(conn: Connection, settings: Settings, workspace_id: UUID, actor: str, pub_id: UUID) -> dict[str, Any]:
    if _row(conn, workspace_id, pub_id) is None:
        raise ValueError("publication_not_found")
    _store_snapshot(conn, settings, workspace_id, pub_id)
    conn.execute(text("UPDATE publication SET status = 'published' WHERE id = :id AND workspace_id = :w"),
                 {"id": pub_id, "w": workspace_id})
    audit.write_audit(conn, workspace_id, actor, "publication.republish", entity="publication", entity_id=str(pub_id))
    return _row(conn, workspace_id, pub_id)


def refresh_workspace(conn: Connection, settings: Settings, workspace_id: UUID, actor: str) -> dict[str, Any]:
    """Regenerate the snapshot of every published publication (automatic update after approved-stat
    changes). Public serving keeps using the last snapshot until this succeeds, so it never goes dark."""
    ids = conn.execute(text("SELECT id FROM publication WHERE workspace_id = :w AND status = 'published'"),
                       {"w": workspace_id}).scalars().all()
    for pid in ids:
        _store_snapshot(conn, settings, workspace_id, pid)
    if ids:
        audit.write_audit(conn, workspace_id, actor, "publication.refresh", entity="workspace",
                          entity_id=str(workspace_id), after={"refreshed": len(ids)})
    return {"refreshed": len(ids)}


def list_publications(conn: Connection, workspace_id: UUID) -> list[dict[str, Any]]:
    rows = conn.execute(
        text("SELECT id, kind, report_id, person_id, title, filters, slug, status, stale, checksum, snapshot_at "
             "FROM publication WHERE workspace_id = :w ORDER BY created_at DESC"), {"w": workspace_id}).mappings().all()
    return [{k: (str(v) if isinstance(v, UUID) else v) for k, v in dict(r).items()} for r in rows]


def get_public(conn: Connection, slug: str) -> dict[str, Any] | None:
    """Resolve a published snapshot by slug with NO workspace context (public, offline-capable). Returns
    None for unknown / unpublished / revoked slugs (so unpublish/revoke make the URL stop resolving)."""
    r = conn.execute(
        text("SELECT title, kind, snapshot, snapshot_html, checksum, snapshot_at FROM publication "
             "WHERE slug = :s AND status = 'published'"), {"s": slug}).mappings().first()
    return dict(r) if r else None


def public_portal(conn: Connection, workspace_id: UUID) -> dict[str, Any]:
    """The public mobile records portal index for a club (Phase 16) — the published reports and profiles,
    read from the publication edge with NO workspace context. Approved, published, non-private data only;
    independent of server uptime (it uses the stored snapshots). Club name/colour come from the snapshots."""
    rows = conn.execute(
        text("SELECT title, kind, slug, snapshot->'branding'->>'club' AS club, "
             "snapshot->'branding'->>'primary' AS primary FROM publication "
             "WHERE workspace_id = :w AND status = 'published' ORDER BY kind DESC, title"),
        {"w": workspace_id}).mappings().all()
    club = next((r["club"] for r in rows if r["club"]), "OneStats")
    primary = next((r["primary"] for r in rows if r["primary"]), "#0b5e3b")
    items = [{"title": r["title"], "kind": r["kind"], "slug": r["slug"],
              "path": f"/api/v1/public/{'p' if r['kind'] == 'player_profile' else 'r'}/{r['slug']}"}
             for r in rows]
    return {"club": club, "primary": primary, "items": items, "workspace_id": str(workspace_id)}


def render_portal_html(portal: dict[str, Any]) -> str:
    """A mobile-first, branded, read-only portal index page (no DB; works offline from snapshots)."""
    primary = escape(str(portal.get("primary") or "#0b5e3b"))
    club = escape(str(portal.get("club") or "OneStats"))
    reports = [i for i in portal["items"] if i["kind"] == "report"]
    players = [i for i in portal["items"] if i["kind"] == "player_profile"]

    def _section(name: str, items: list[dict[str, Any]]) -> str:
        if not items:
            return ""
        links = "".join(
            f"<li data-name='{escape(i['title'].lower())}'><a href='{escape(i['path'])}'>{escape(i['title'])}</a></li>"
            for i in items)
        return f"<h2>{escape(name)}</h2><ul class='list'>{links}</ul>"

    body = _section("Players", players) + _section("Reports", reports)
    if not portal["items"]:
        body = "<p class='muted'>No published records yet.</p>"
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{club} — Records</title>
<style>
:root{{--brand:{primary}}}
*{{box-sizing:border-box}}
body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0;color:#17201c;background:#f7f9f8}}
header{{background:var(--brand);color:#fff;padding:16px;position:sticky;top:0}}
header h1{{margin:0;font-size:18px}}
main{{max-width:680px;margin:0 auto;padding:16px}}
.search{{width:100%;padding:12px;font-size:16px;border:1px solid #d8dcd9;border-radius:10px;margin-bottom:12px}}
h2{{color:var(--brand);font-size:15px;margin:18px 0 6px}}
.list{{list-style:none;padding:0;margin:0}}
.list li{{background:#fff;border:1px solid #e5eae7;border-radius:10px;margin-bottom:8px}}
.list a{{display:block;padding:14px 16px;color:#17201c;text-decoration:none;font-size:16px}}
.list a:active{{background:#eef3f0}}
.muted{{color:#5b665f}} footer{{color:#8a938d;font-size:11px;text-align:center;padding:16px}}
</style></head><body>
<header><h1>{club} — Records</h1></header>
<main>
<input class="search" type="search" placeholder="Search players and reports…" aria-label="Search"
 oninput="var q=this.value.toLowerCase();document.querySelectorAll('.list li').forEach(function(li){{li.style.display=li.dataset.name.indexOf(q)>-1?'':'none'}})">
{body}
</main>
<footer>Read-only records portal · published by OneStats</footer>
</body></html>"""


def static_export(conn: Connection, workspace_id: UUID, pub_id: UUID) -> dict[str, str]:
    """The self-contained files for uploading to existing website hosting: a JSON feed + an HTML page."""
    row = _row(conn, workspace_id, pub_id)
    if row is None or row.get("snapshot") is None:
        raise ValueError("publication_not_found")
    snap = row["snapshot"] if isinstance(row["snapshot"], dict) else json.loads(row["snapshot"])
    return {f"{row['slug']}.json": json.dumps({"title": row["title"], **snap}, indent=2, default=str),
            f"{row['slug']}.html": row["snapshot_html"] or ""}
