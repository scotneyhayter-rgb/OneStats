"""Player participation & statistical attribution — Phase 6 foundation.

Read-only helpers that demonstrate (and lock in, via tests) the attribution rules the
comprehensive statistics engine (Phase 12) will build on. They are intentionally small — not the
reporting engine — but they prove the data model already attributes performances correctly:

* A performance is attributed to the **team the player actually represented in that match** — the
  innings' batting/bowling team — NOT the player's registered/affiliated club. So a fill-in or
  guest appearance counts for the team represented, never for the player's home club.
* **Career** totals follow the player's single identity (``person_id``) across every team/club and
  count each appearance **once** (no duplication, no fragmentation).
* A temporary/transfer affiliation is only a roster hint; it never changes attribution and never
  rewrites earlier matches.

Catch/stumping/run-out credit uses ``batting_entry.fielder_person_id`` on the relevant dismissal
type; a fielding credit belongs to the fielding side (the innings' bowling team). Everything is
workspace-scoped (RLS); all functions are read-only.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

_CATCH_TYPES = ("caught", "caught_behind")


def team_season_players(conn: Connection, team_id: UUID, season_id: UUID | None = None) -> list[dict[str, Any]]:
    """Players to suggest for a side in a match: those affiliated to the team (or its club) whose
    validity overlaps the season, UNION those who have appeared (batted/bowled) for that team in the
    season. Deduplicated by identity; each row flags how it was reached and whether the affiliation
    is temporary. The UI offers a separate 'search everyone' path for guests/transfers."""
    org = conn.execute(text("SELECT organisation_id FROM team WHERE id = :t"), {"t": team_id}).scalar_one_or_none()
    if org is None:
        raise ValueError("team_not_found")
    season = None
    if season_id is not None:
        season = conn.execute(
            text("SELECT start_date, end_date FROM season WHERE id = :s"), {"s": season_id}
        ).mappings().first()

    aff_sql = ("SELECT person_id, is_temporary FROM person_affiliation "
               "WHERE status = 'active' AND (team_id = :t OR (team_id IS NULL AND organisation_id = :o))")
    params: dict[str, Any] = {"t": team_id, "o": org}
    if season and season["start_date"] and season["end_date"]:
        aff_sql += " AND (valid_from IS NULL OR valid_from <= :se) AND (valid_to IS NULL OR valid_to >= :ss)"
        params["se"] = season["end_date"]
        params["ss"] = season["start_date"]
    affiliated: dict[Any, bool] = {}
    for r in conn.execute(text(aff_sql), params).mappings():
        # a person may have several affiliations; treat as temporary only if ALL are temporary
        affiliated[r["person_id"]] = affiliated.get(r["person_id"], True) and bool(r["is_temporary"])

    app_params: dict[str, Any] = {"t": team_id}
    season_clause = ""
    if season_id is not None:
        season_clause = " AND m.season_id = :s"
        app_params["s"] = season_id
    appeared: set[Any] = set()
    for sql in (
        (f"SELECT be.person_id AS pid FROM batting_entry be JOIN innings i ON i.id = be.innings_id "
         f"JOIN match m ON m.id = i.match_id WHERE i.batting_team_id = :t AND be.person_id IS NOT NULL{season_clause}"),
        (f"SELECT bo.person_id AS pid FROM bowling_entry bo JOIN innings i ON i.id = bo.innings_id "
         f"JOIN match m ON m.id = i.match_id WHERE i.bowling_team_id = :t AND bo.person_id IS NOT NULL{season_clause}"),
    ):
        for row in conn.execute(text(sql), app_params):
            appeared.add(row[0])

    ids = set(affiliated) | appeared
    if not ids:
        return []
    rows = conn.execute(
        text("SELECT id, display_name, is_junior FROM person WHERE id = ANY(:ids) AND merged_into_id IS NULL "
             "ORDER BY display_name"),
        {"ids": list(ids)},
    ).mappings().all()
    return [{
        "person_id": r["id"], "display_name": r["display_name"], "is_junior": r["is_junior"],
        "affiliated": r["id"] in affiliated, "appeared": r["id"] in appeared,
        "is_temporary": bool(affiliated.get(r["id"], False)),
    } for r in rows]


def player_appearances(conn: Connection, person_id: UUID) -> list[dict[str, Any]]:
    """Every match the player appeared in, with the team/club they represented and that match's
    season — the basis of the profile's 'appearances for different teams and clubs' view. Each
    (match, team) appears once."""
    rows = conn.execute(
        text(
            "SELECT DISTINCT a.match_id, a.team_id, t.organisation_id, m.season_id, m.match_date "
            "FROM ( "
            "  SELECT i.match_id, i.batting_team_id AS team_id FROM batting_entry be "
            "    JOIN innings i ON i.id = be.innings_id WHERE be.person_id = :p AND i.batting_team_id IS NOT NULL "
            "  UNION "
            "  SELECT i.match_id, i.bowling_team_id FROM bowling_entry bo "
            "    JOIN innings i ON i.id = bo.innings_id WHERE bo.person_id = :p AND i.bowling_team_id IS NOT NULL "
            ") a JOIN match m ON m.id = a.match_id LEFT JOIN team t ON t.id = a.team_id "
            "ORDER BY m.match_date NULLS LAST"
        ),
        {"p": person_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def _scalar(conn: Connection, sql: str, params: dict[str, Any]) -> int:
    v = conn.execute(text(sql), params).scalar_one()
    return int(v) if v is not None else 0


def player_career_totals(conn: Connection, person_id: UUID) -> dict[str, Any]:
    """Career totals following the single identity across ALL teams/clubs; each appearance counted
    once (no duplication or fragmentation)."""
    p = {"p": person_id}
    catch_in = ", ".join(f"'{c}'" for c in _CATCH_TYPES)
    return {
        "person_id": str(person_id),
        "matches": _scalar(conn,
            "SELECT count(DISTINCT i.match_id) FROM innings i WHERE i.id IN "
            "(SELECT innings_id FROM batting_entry WHERE person_id = :p "
            " UNION SELECT innings_id FROM bowling_entry WHERE person_id = :p)", p),
        "runs": _scalar(conn, "SELECT coalesce(sum(runs),0) FROM batting_entry WHERE person_id = :p AND runs IS NOT NULL", p),
        "wickets": _scalar(conn, "SELECT coalesce(sum(wickets),0) FROM bowling_entry WHERE person_id = :p AND wickets IS NOT NULL", p),
        "catches": _scalar(conn, f"SELECT count(*) FROM batting_entry WHERE fielder_person_id = :p AND dismissal_type IN ({catch_in})", p),
        "stumpings": _scalar(conn, "SELECT count(*) FROM batting_entry WHERE fielder_person_id = :p AND dismissal_type = 'stumped'", p),
        "run_outs": _scalar(conn, "SELECT count(*) FROM batting_entry WHERE fielder_person_id = :p AND dismissal_type = 'run_out'", p),
    }


def player_team_totals(conn: Connection, person_id: UUID, team_id: UUID, season_id: UUID | None = None) -> dict[str, Any]:
    """A player's performances ATTRIBUTED to a specific team (the team represented in the innings).
    This is what a club/team report draws on — a fill-in's runs count for the team represented, not
    the player's home club."""
    sc = " AND m.season_id = :s" if season_id is not None else ""
    base = {"p": person_id, "t": team_id}
    if season_id is not None:
        base["s"] = season_id
    catch_in = ", ".join(f"'{c}'" for c in _CATCH_TYPES)
    return {
        "person_id": str(person_id), "team_id": str(team_id),
        "runs": _scalar(conn,
            f"SELECT coalesce(sum(be.runs),0) FROM batting_entry be JOIN innings i ON i.id = be.innings_id "
            f"JOIN match m ON m.id = i.match_id WHERE be.person_id = :p AND i.batting_team_id = :t AND be.runs IS NOT NULL{sc}", base),
        "wickets": _scalar(conn,
            f"SELECT coalesce(sum(bo.wickets),0) FROM bowling_entry bo JOIN innings i ON i.id = bo.innings_id "
            f"JOIN match m ON m.id = i.match_id WHERE bo.person_id = :p AND i.bowling_team_id = :t AND bo.wickets IS NOT NULL{sc}", base),
        "catches": _scalar(conn,
            f"SELECT count(*) FROM batting_entry be JOIN innings i ON i.id = be.innings_id JOIN match m ON m.id = i.match_id "
            f"WHERE be.fielder_person_id = :p AND i.bowling_team_id = :t AND be.dismissal_type IN ({catch_in}){sc}", base),
    }


def team_totals(conn: Connection, team_id: UUID, season_id: UUID | None = None) -> dict[str, Any]:
    """A team's batting/bowling totals, attributed by the innings' team (all players who represented
    it, registered or fill-in)."""
    sc = " AND m.season_id = :s" if season_id is not None else ""
    base: dict[str, Any] = {"t": team_id}
    if season_id is not None:
        base["s"] = season_id
    return {
        "team_id": str(team_id),
        "runs": _scalar(conn,
            f"SELECT coalesce(sum(be.runs),0) FROM batting_entry be JOIN innings i ON i.id = be.innings_id "
            f"JOIN match m ON m.id = i.match_id WHERE i.batting_team_id = :t AND be.runs IS NOT NULL{sc}", base),
        "wickets": _scalar(conn,
            f"SELECT coalesce(sum(bo.wickets),0) FROM bowling_entry bo JOIN innings i ON i.id = bo.innings_id "
            f"JOIN match m ON m.id = i.match_id WHERE i.bowling_team_id = :t AND bo.wickets IS NOT NULL{sc}", base),
    }
