"""Life Members & honorary recognition (Phase 13, Stage 13.8).

Explicitly recorded, authorised honours — never inferred from statistics. Managed by authorised
administrators; each may carry an awarding organisation, date/season, evidence and a linked photograph.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain import audit

TYPES = ("life_member", "honorary_member", "club_award", "historical_figure", "other")
_FIELDS = ("person_id", "awarded_date", "awarded_season", "awarding_organisation_id", "description",
           "evidence", "media_asset_id", "notes", "status", "award_category")


def create_honour(conn: Connection, workspace_id: UUID, actor: str, *, honour_type: str, title: str,
                  **meta: Any) -> dict[str, Any]:
    if honour_type not in TYPES:
        raise ValueError("invalid_honour_type")
    if not (title or "").strip():
        raise ValueError("title_required")
    cols = ["workspace_id", "honour_type", "title", "created_by"]
    vals = [":w", ":ht", ":t", ":by"]
    params: dict[str, Any] = {"w": workspace_id, "ht": honour_type, "t": title, "by": actor}
    for k in _FIELDS:
        if k in meta and meta[k] is not None:
            cols.append(k)
            vals.append(f":{k}")
            params[k] = meta[k]
    hid = conn.execute(
        text(f"INSERT INTO honour({', '.join(cols)}) VALUES ({', '.join(vals)}) RETURNING id"), params
    ).scalar_one()
    audit.write_audit(conn, workspace_id, actor, "records.honour_created", entity="honour",
                      entity_id=str(hid), after={"honour_type": honour_type, "title": title})
    return get_honour(conn, hid)


def get_honour(conn: Connection, honour_id: UUID) -> dict[str, Any] | None:
    r = conn.execute(text("SELECT * FROM honour WHERE id = :id"), {"id": honour_id}).mappings().first()
    return dict(r) if r else None


def list_honours(conn: Connection, workspace_id: UUID, *, honour_type: str | None = None,
                 person_id: UUID | None = None) -> list[dict[str, Any]]:
    sql = "SELECT * FROM honour WHERE workspace_id = :w"
    params: dict[str, Any] = {"w": workspace_id}
    if honour_type:
        sql += " AND honour_type = :ht"
        params["ht"] = honour_type
    if person_id:
        sql += " AND person_id = :p"
        params["p"] = person_id
    sql += " ORDER BY awarded_date DESC NULLS LAST, title"
    return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]


def list_honorary_members(conn: Connection, workspace_id: UUID) -> list[dict[str, Any]]:
    """Every recorded honour/honorary recognition for the Records "Life Members & honorary recognition"
    list, from BOTH stores: the dedicated ``honour`` table AND per-person ``person_recognition`` entries
    that record a life membership / honorary recognition (what the People screen writes). Members recorded
    either way now appear here. Each row carries the person's name; nothing is inferred from statistics."""
    honour_rows = conn.execute(
        text("SELECT h.honour_type, h.title, h.person_id, p.display_name AS person, "
             "h.awarded_season, h.status, 'honour' AS source "
             "FROM honour h LEFT JOIN person p ON p.id = h.person_id "
             "WHERE h.workspace_id = :w"),
        {"w": workspace_id},
    ).mappings().all()
    # person_recognition rows that denote a life membership or honorary recognition (free-text type/title).
    recog_rows = conn.execute(
        text("SELECT r.recognition_type, r.title, r.person_id, p.display_name AS person, r.season_label "
             "FROM person_recognition r JOIN person p ON p.id = r.person_id "
             "WHERE r.workspace_id = :w AND ("
             "r.recognition_type ILIKE '%life member%' OR r.title ILIKE '%life member%' "
             "OR r.recognition_type ILIKE '%honorary%' OR r.title ILIKE '%honorary%' "
             "OR r.recognition_type ILIKE '%life mem%')"),
        {"w": workspace_id},
    ).mappings().all()

    out: list[dict[str, Any]] = []
    seen: set[tuple[Any, str]] = set()
    for h in honour_rows:
        key = (h["person_id"], str(h["honour_type"]).lower())
        seen.add(key)
        out.append({"honour_type": h["honour_type"], "title": h["title"], "person_id": h["person_id"],
                    "person": h["person"], "awarded_season": h["awarded_season"], "status": h["status"],
                    "source": "honour"})
    for r in recog_rows:
        label = f"{r['recognition_type'] or ''} {r['title'] or ''}".lower()
        inferred = "life_member" if "life" in label else "honorary_member"
        key = (r["person_id"], inferred)
        if key in seen:   # already recorded as a dedicated honour — do not list twice
            continue
        seen.add(key)
        out.append({"honour_type": inferred, "title": r["title"] or r["recognition_type"],
                    "person_id": r["person_id"], "person": r["person"],
                    "awarded_season": r["season_label"], "status": "confirmed", "source": "recognition"})
    out.sort(key=lambda x: ((x.get("person") or "").lower(), str(x.get("honour_type"))))
    return out


def update_honour(conn: Connection, workspace_id: UUID, actor: str, honour_id: UUID, **fields: Any) -> dict[str, Any]:
    if get_honour(conn, honour_id) is None:
        raise ValueError("honour_not_found")
    if "status" in fields and fields["status"] not in ("proposed", "confirmed"):
        raise ValueError("invalid_status")
    allowed = ("title", *_FIELDS)
    sets, params = [], {"id": honour_id}
    for k in allowed:
        if k in fields and fields[k] is not None:
            sets.append(f"{k} = :{k}")
            params[k] = fields[k]
    if sets:
        sets.append("updated_at = now()")
        conn.execute(text(f"UPDATE honour SET {', '.join(sets)} WHERE id = :id"), params)
        audit.write_audit(conn, workspace_id, actor, "records.honour_updated", entity="honour",
                          entity_id=str(honour_id), after={k: params[k] for k in params if k != "id"})
    return get_honour(conn, honour_id)
