"""Comprehensive player profiles (Phase 5, Stage 4).

Profile detail, player numbers, leadership history, recognition and photograph metadata, all
hanging off the stable ``person_id`` (Stages 1-3). Affiliations/participation come from Stage 2;
nothing here re-implements identity. **No career statistics are stored** — figures are computed
from verified match records later, so this exposes only a reserved integration *contract*
(:func:`career_statistics_contract`) with every value marked not-yet-available.

Privacy: junior/personal data stays protected (Stage 1 ``person.privacy_protected``); ``public``
serialisation strips internal research notes and anything not explicitly ``public_visible`` —
a profile being available internally never makes it public. Governed by ``person.manage``; audited.
Life Membership and other recognition stay tied to their awarding organisation and never transfer
automatically on a merger.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain import affiliations, audit, people

# Reserved career-statistics contract — keys computed from verified match records in later phases.
STAT_KEYS = (
    "matches_played", "runs_scored", "batting_average", "centuries", "half_centuries",
    "wickets_taken", "bowling_average", "five_wicket_innings", "catches", "run_outs",
    "stumpings", "matches_captained", "captaincy_wins", "captaincy_win_pct",
    "partnerships", "finals_records", "seasonal_awards_milestones",
)
PLAYER_STATUSES = ("current", "former", "unknown")
VERIFICATION_STATUSES = ("unverified", "supported", "verified", "disputed", "corrected")
_INTERNAL_FIELDS = ("research_notes",)

_PROFILE_COLS = (
    "id, person_id, full_name, preferred_display_name, biography, research_notes, date_of_death, "
    "dod_precision, batting_style, bowling_style, is_wicketkeeper, career_start, career_end, "
    "player_status, verification_status, public_visible, created_at, updated_at"
)


def career_statistics_contract(person_id: UUID) -> dict[str, Any]:
    """The reserved statistics interface — never fabricated. Every figure is ``None`` with status
    ``not_available`` until the statistics engines compute it from verified match records."""
    return {
        "person_id": str(person_id),
        "source": "computed_from_verified_records",
        "status": "not_available",
        "statistics": {k: {"value": None, "status": "not_available"} for k in STAT_KEYS},
    }


# --------------------------------------------------------------------------- profile (1:1)


def get_profile(conn: Connection, person_id: UUID) -> dict[str, Any] | None:
    r = conn.execute(
        text(f"SELECT {_PROFILE_COLS} FROM person_profile WHERE person_id = :p"), {"p": person_id}
    ).mappings().first()
    return dict(r) if r else None


_PROFILE_FIELDS = {
    "full_name", "preferred_display_name", "biography", "research_notes", "date_of_death",
    "dod_precision", "batting_style", "bowling_style", "is_wicketkeeper", "career_start",
    "career_end", "player_status", "verification_status", "public_visible",
}


def upsert_profile(
    conn: Connection, workspace_id: UUID, actor: str, person_id: UUID, **fields: Any
) -> dict[str, Any]:
    """Create or update the 1:1 profile for a person. Only provided fields are written."""
    if people.get_person(conn, person_id, include_protected=True) is None:
        raise ValueError("person_not_found")
    if fields.get("player_status") is not None and fields["player_status"] not in PLAYER_STATUSES:
        raise ValueError("invalid_player_status")
    if fields.get("verification_status") is not None and fields["verification_status"] not in VERIFICATION_STATUSES:
        raise ValueError("invalid_verification_status")
    data = {k: v for k, v in fields.items() if k in _PROFILE_FIELDS and v is not None}
    before = get_profile(conn, person_id)
    if before is None:
        cols = ["workspace_id", "person_id", *data.keys()]
        vals = [":w", ":p", *(f":{k}" for k in data)]
        conn.execute(
            text(f"INSERT INTO person_profile({', '.join(cols)}) VALUES ({', '.join(vals)})"),
            {"w": workspace_id, "p": person_id, **data},
        )
        action = "person_profile.create"
    elif data:
        sets = ", ".join(f"{k} = :{k}" for k in data)
        conn.execute(
            text(f"UPDATE person_profile SET {sets}, updated_at = now() WHERE person_id = :p"),
            {**data, "p": person_id},
        )
        action = "person_profile.update"
    else:
        return before
    after = get_profile(conn, person_id)
    audit.write_audit(conn, workspace_id, actor, action, entity="person", entity_id=str(person_id),
                      before=before, after=after)
    return after


# --------------------------------------------------------------------------- child records


def _insert(conn: Connection, table: str, workspace_id: UUID, person_id: UUID, data: dict[str, Any]) -> UUID:
    cols = ["workspace_id", "person_id", *data.keys()]
    vals = [":w", ":p", *(f":{k}" for k in data)]
    return conn.execute(
        text(f"INSERT INTO {table}({', '.join(cols)}) VALUES ({', '.join(vals)}) RETURNING id"),
        {"w": workspace_id, "p": person_id, **data},
    ).scalar_one()


def add_number(
    conn: Connection, workspace_id: UUID, actor: str, person_id: UUID, *, organisation_id: UUID,
    number: str | None = None, season_label: str | None = None, valid_from: Any | None = None,
    valid_to: Any | None = None, note: str | None = None,
    source_system: str | None = None, source_ref: str | None = None,
) -> UUID:
    if people.get_person(conn, person_id, include_protected=True) is None:
        raise ValueError("person_not_found")
    if conn.execute(text("SELECT 1 FROM organisation WHERE id = :o"), {"o": organisation_id}).first() is None:
        raise ValueError("organisation_not_found")
    nid = _insert(conn, "person_number", workspace_id, person_id, {
        "organisation_id": organisation_id, "number": number, "season_label": season_label,
        "valid_from": valid_from, "valid_to": valid_to, "note": note,
        "source_system": source_system, "source_ref": source_ref,
    })
    audit.write_audit(conn, workspace_id, actor, "person_number.add", entity="person",
                      entity_id=str(person_id), after={"number": number, "organisation_id": str(organisation_id)})
    return nid


def list_numbers(conn: Connection, person_id: UUID) -> list[dict[str, Any]]:
    rows = conn.execute(
        text("SELECT id, organisation_id, number, season_label, valid_from, valid_to, note "
             "FROM person_number WHERE person_id = :p ORDER BY valid_from NULLS FIRST, created_at"),
        {"p": person_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def add_leadership(
    conn: Connection, workspace_id: UUID, actor: str, person_id: UUID, *, organisation_id: UUID,
    role: str, team_id: UUID | None = None, season_label: str | None = None,
    valid_from: Any | None = None, valid_to: Any | None = None, note: str | None = None,
    source_system: str | None = None, source_ref: str | None = None,
) -> UUID:
    role = (role or "").strip()
    if not role:
        raise ValueError("missing_role")
    if people.get_person(conn, person_id, include_protected=True) is None:
        raise ValueError("person_not_found")
    if conn.execute(text("SELECT 1 FROM organisation WHERE id = :o"), {"o": organisation_id}).first() is None:
        raise ValueError("organisation_not_found")
    lid = _insert(conn, "person_leadership", workspace_id, person_id, {
        "organisation_id": organisation_id, "team_id": team_id, "role": role,
        "season_label": season_label, "valid_from": valid_from, "valid_to": valid_to, "note": note,
        "source_system": source_system, "source_ref": source_ref,
    })
    audit.write_audit(conn, workspace_id, actor, "person_leadership.add", entity="person",
                      entity_id=str(person_id), after={"role": role, "organisation_id": str(organisation_id)})
    return lid


def list_leadership(conn: Connection, person_id: UUID) -> list[dict[str, Any]]:
    rows = conn.execute(
        text("SELECT id, organisation_id, team_id, role, season_label, valid_from, valid_to, note "
             "FROM person_leadership WHERE person_id = :p ORDER BY valid_from NULLS FIRST, created_at"),
        {"p": person_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def add_recognition(
    conn: Connection, workspace_id: UUID, actor: str, person_id: UUID, *, recognition_type: str,
    organisation_id: UUID | None = None, title: str | None = None, awarded_on: Any | None = None,
    season_label: str | None = None, evidence: str | None = None, notes: str | None = None,
    source_system: str | None = None, source_ref: str | None = None,
) -> UUID:
    recognition_type = (recognition_type or "").strip()
    if not recognition_type:
        raise ValueError("missing_recognition_type")
    if people.get_person(conn, person_id, include_protected=True) is None:
        raise ValueError("person_not_found")
    if organisation_id is not None and conn.execute(
        text("SELECT 1 FROM organisation WHERE id = :o"), {"o": organisation_id}
    ).first() is None:
        raise ValueError("organisation_not_found")
    rid = _insert(conn, "person_recognition", workspace_id, person_id, {
        "organisation_id": organisation_id, "recognition_type": recognition_type, "title": title,
        "awarded_on": awarded_on, "season_label": season_label, "evidence": evidence, "notes": notes,
        "source_system": source_system, "source_ref": source_ref,
    })
    audit.write_audit(conn, workspace_id, actor, "person_recognition.add", entity="person",
                      entity_id=str(person_id),
                      after={"recognition_type": recognition_type, "organisation_id": str(organisation_id) if organisation_id else None})
    return rid


def list_recognition(conn: Connection, person_id: UUID) -> list[dict[str, Any]]:
    rows = conn.execute(
        text("SELECT id, organisation_id, recognition_type, title, awarded_on, season_label, "
             "evidence, notes FROM person_recognition WHERE person_id = :p "
             "ORDER BY awarded_on NULLS FIRST, created_at"),
        {"p": person_id},
    ).mappings().all()
    return [dict(r) for r in rows]


_ATTR_TABLE = {"number": "person_number", "leadership": "person_leadership", "recognition": "person_recognition"}


def delete_attribute(conn: Connection, workspace_id: UUID, actor: str, person_id: UUID, kind: str,
                     attr_id: UUID) -> None:
    """Delete one squad number / leadership / recognition entry (so they can be corrected as years change
    or new information comes in). Scoped to the workspace and person; audited."""
    table = _ATTR_TABLE.get(kind)
    if table is None:
        raise ValueError("invalid_kind")
    res = conn.execute(
        text(f"DELETE FROM {table} WHERE id = :id AND workspace_id = :w AND person_id = :p RETURNING id"),
        {"id": attr_id, "w": workspace_id, "p": person_id}).first()
    if res is None:
        raise ValueError("not_found")
    audit.write_audit(conn, workspace_id, actor, f"person_{kind}.delete", entity="person",
                      entity_id=str(person_id), after={"deleted": str(attr_id)})


# --------------------------------------------------------------------------- photos (metadata)


def register_photo(
    conn: Connection, workspace_id: UUID, actor: str, person_id: UUID, *, media_key: str,
    is_primary: bool = False, caption: str | None = None, approx_date: str | None = None,
    source_attribution: str | None = None, usage_permissions: str | None = None,
    public_visible: bool = False, width: int | None = None, height: int | None = None,
    format: str | None = None,
) -> UUID:
    if people.get_person(conn, person_id, include_protected=True) is None:
        raise ValueError("person_not_found")
    if is_primary:
        conn.execute(
            text("UPDATE person_photo SET is_primary = false WHERE person_id = :p"), {"p": person_id}
        )
    pid = _insert(conn, "person_photo", workspace_id, person_id, {
        "media_key": media_key, "is_primary": is_primary, "caption": caption, "approx_date": approx_date,
        "source_attribution": source_attribution, "usage_permissions": usage_permissions,
        "public_visible": public_visible, "width": width, "height": height, "format": format,
    })
    audit.write_audit(conn, workspace_id, actor, "person_photo.register", entity="person",
                      entity_id=str(person_id), after={"media_key": media_key, "is_primary": is_primary})
    return pid


def list_photos(conn: Connection, person_id: UUID) -> list[dict[str, Any]]:
    rows = conn.execute(
        text("SELECT id, media_key, is_primary, caption, approx_date, source_attribution, "
             "usage_permissions, public_visible, width, height, format FROM person_photo "
             "WHERE person_id = :p ORDER BY is_primary DESC, created_at"),
        {"p": person_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def get_photo(conn: Connection, photo_id: UUID) -> dict[str, Any] | None:
    r = conn.execute(
        text("SELECT id, person_id, media_key, is_primary, public_visible FROM person_photo WHERE id = :id"),
        {"id": photo_id},
    ).mappings().first()
    return dict(r) if r else None


def delete_photo(conn: Connection, workspace_id: UUID, actor: str, photo_id: UUID) -> dict[str, Any] | None:
    row = get_photo(conn, photo_id)
    if row is None:
        raise ValueError("photo_not_found")
    conn.execute(text("DELETE FROM person_photo WHERE id = :id"), {"id": photo_id})
    audit.write_audit(conn, workspace_id, actor, "person_photo.delete", entity="person",
                      entity_id=str(row["person_id"]), before={"media_key": row["media_key"]})
    return row  # caller removes the stored file by media_key


# --------------------------------------------------------------------------- career view


def _related_organisations(conn: Connection, org_ids: set[UUID]) -> list[dict[str, Any]]:
    """Documented (non-void) organisation relationships touching the player's orgs — surfaced so a
    combined report can be offered only where an approved relationship exists; never auto-merged."""
    if not org_ids:
        return []
    rows = conn.execute(
        text(
            "SELECT id, from_org_id, to_org_id, rel_type, valid_from, valid_to FROM organisation_relationship "
            "WHERE is_void = false AND (from_org_id = ANY(:ids) OR to_org_id = ANY(:ids))"
        ),
        {"ids": list(org_ids)},
    ).mappings().all()
    return [dict(r) for r in rows]


def career_view(conn: Connection, person_id: UUID, *, public: bool = False) -> dict[str, Any] | None:
    """Assemble the full profile for the (future) Player Profile screen: identity, profile detail,
    names, roles, affiliations (by organisation/season), numbers, leadership, recognition, photos,
    documented related organisations, and the reserved statistics contract. ``public=True`` returns
    only public-authorised, non-internal fields and nothing for a privacy-protected person."""
    include_protected = not public
    person = people.detail(conn, person_id, include_protected=include_protected)
    if person is None:
        return None
    profile = get_profile(conn, person_id)
    affs = affiliations.list_affiliations(conn, person_id=person_id)
    org_ids = {a["organisation_id"] for a in affs}
    photos = list_photos(conn, person_id)

    if public:
        # Internal profile existing never implies public visibility.
        if person.get("privacy_protected"):
            return None
        if profile is not None:
            if not profile.get("public_visible"):
                profile = None
            else:
                profile = {k: v for k, v in profile.items() if k not in _INTERNAL_FIELDS}
        photos = [p for p in photos if p.get("public_visible")]

    return {
        "person": person,
        "profile": profile,
        "affiliations": affs,
        "numbers": list_numbers(conn, person_id),
        "leadership": list_leadership(conn, person_id),
        "recognition": list_recognition(conn, person_id),
        "photos": photos,
        "related_organisations": [] if public else _related_organisations(conn, org_ids),
        "statistics": career_statistics_contract(person_id),
    }
