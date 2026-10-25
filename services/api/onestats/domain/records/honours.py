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
