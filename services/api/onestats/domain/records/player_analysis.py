"""Player career analysis for the profile (Phase 13 follow-up).

A OneStats-native representation of a player's career — performance splits (by opposition / ground / grade /
format), best batting innings and best bowling figures, top partnerships, dismissal analysis (how out, and
who dismissed them), and chart series (innings run-scores, score frequency). Built from the player's own
per-innings batting/bowling records in approved, statistics-eligible matches, via the one engine's source
data — nothing is invented, and unknown is never treated as zero. Not a copy of any external tool; a curated
subset for OneStats.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain.records.player_profile import _merge_ids

_NON_INNINGS = ("dnb", "absent")                     # not a batting innings
_APPROVED = "m.approval_status IN ('approved','verified_partial') AND m.include_in_statistics = true"


def _names(conn: Connection, workspace_id: UUID) -> dict[str, str]:
    return {str(r["id"]): r["display_name"] for r in conn.execute(
        text("SELECT id, display_name FROM person WHERE workspace_id = :w"), {"w": workspace_id}).mappings()}


def _batting_innings(conn: Connection, workspace_id: UUID, ids: list[str]) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(
            "SELECT be.runs, be.balls_faced AS balls, be.dismissal_type AS dt, be.bowler_person_id AS bowler, "
            " be.fielder_person_id AS fielder, be.batting_position AS pos, "
            " m.id AS match_id, m.match_date, m.format, g.name AS grade, v.name AS ground, "
            " (SELECT coalesce(nullif(o.short_name,''), o.name) FROM match_team mt "
            "  JOIN team t ON t.id = mt.team_id JOIN organisation o ON o.id = t.organisation_id "
            "  WHERE mt.match_id = m.id AND mt.team_id <> i.batting_team_id LIMIT 1) AS opposition "
            "FROM batting_entry be JOIN innings i ON i.id = be.innings_id JOIN match m ON m.id = i.match_id "
            "LEFT JOIN grade g ON g.id = m.grade_id LEFT JOIN venue v ON v.id = m.venue_id "
            f"WHERE be.person_id = ANY(CAST(:ids AS uuid[])) AND m.workspace_id = :w AND {_APPROVED} "
            "  AND (be.dismissal_type IS NULL OR be.dismissal_type NOT IN ('dnb','absent'))"
        ),
        {"ids": ids, "w": workspace_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def _bowling_innings(conn: Connection, workspace_id: UUID, ids: list[str]) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(
            "SELECT bo.wickets, bo.runs_conceded AS runs, bo.legal_balls AS balls, bo.maidens, "
            " m.id AS match_id, m.match_date, m.format, g.name AS grade, v.name AS ground, "
            " (SELECT coalesce(nullif(o.short_name,''), o.name) FROM match_team mt "
            "  JOIN team t ON t.id = mt.team_id JOIN organisation o ON o.id = t.organisation_id "
            "  WHERE mt.match_id = m.id AND mt.team_id <> i.bowling_team_id LIMIT 1) AS opposition "
            "FROM bowling_entry bo JOIN innings i ON i.id = bo.innings_id JOIN match m ON m.id = i.match_id "
            "LEFT JOIN grade g ON g.id = m.grade_id LEFT JOIN venue v ON v.id = m.venue_id "
            f"WHERE bo.person_id = ANY(CAST(:ids AS uuid[])) AND m.workspace_id = :w AND {_APPROVED}"
        ),
        {"ids": ids, "w": workspace_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def _dim(row: dict[str, Any], dimension: str) -> str:
    val = {"opposition": row.get("opposition"), "ground": row.get("ground"),
           "grade": row.get("grade"), "format": row.get("format")}.get(dimension)
    return str(val) if val else "Unknown"


def _is_out(dt: Any) -> bool:
    return dt is not None and dt not in ("not_out", "retired_not_out")


def _overs(balls: int) -> str:
    return f"{balls // 6}.{balls % 6}" if balls else "0.0"


def _bat_agg(rows: list[dict[str, Any]]) -> dict[str, Any]:
    matches = len({r["match_id"] for r in rows})
    inns = len(rows)
    runs = sum(r["runs"] for r in rows if r["runs"] is not None)
    dismissed = sum(1 for r in rows if _is_out(r["dt"]))
    not_outs = sum(1 for r in rows if r["dt"] in ("not_out", "retired_not_out"))
    hs_rows = [r for r in rows if r["runs"] is not None]
    hs = max((r["runs"] for r in hs_rows), default=None)
    hs_no = any(r["runs"] == hs and not _is_out(r["dt"]) for r in hs_rows) if hs is not None else False
    fifties = sum(1 for r in hs_rows if 50 <= (r["runs"] or 0) < 100)
    hundreds = sum(1 for r in hs_rows if (r["runs"] or 0) >= 100)
    return {"matches": matches, "innings": inns, "runs": runs, "not_outs": not_outs,
            "average": round(runs / dismissed, 2) if dismissed else None,
            "high_score": (f"{hs}*" if hs_no else str(hs)) if hs is not None else None,
            "fifties": fifties, "hundreds": hundreds}


def _bowl_agg(rows: list[dict[str, Any]]) -> dict[str, Any]:
    matches = len({r["match_id"] for r in rows})
    balls = sum(r["balls"] or 0 for r in rows)
    runs = sum(r["runs"] or 0 for r in rows if r["runs"] is not None)
    wkts = sum(r["wickets"] or 0 for r in rows if r["wickets"] is not None)
    maidens = sum(r["maidens"] or 0 for r in rows)
    best = max(((r["wickets"] or 0, -(r["runs"] if r["runs"] is not None else 10 ** 6), r) for r in rows),
              default=None)
    bbi = f"{best[2]['wickets']}-{best[2]['runs']}" if best and best[2].get("wickets") else None
    return {"matches": matches, "overs": _overs(balls), "maidens": maidens, "runs": runs, "wickets": wkts,
            "average": round(runs / wkts, 2) if wkts else None,
            "economy": round(runs / (balls / 6), 2) if balls else None,
            "best": bbi}


def _split(rows: list[dict[str, Any]], dimension: str, agg) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        groups.setdefault(_dim(r, dimension), []).append(r)
    out = [{"label": label, **agg(grp)} for label, grp in groups.items()]
    out.sort(key=lambda x: (-(x.get("runs") or 0), x["label"]))
    return out


def _best_batting(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    scored = [r for r in rows if r["runs"] is not None]
    scored.sort(key=lambda r: (-(r["runs"]), _is_out(r["dt"])))     # most runs; not-out ranks above out on a tie
    return [{"score": f"{r['runs']}{'' if _is_out(r['dt']) else '*'}", "runs": r["runs"],
             "opposition": r["opposition"], "ground": r["ground"],
             "date": r["match_date"].isoformat() if r["match_date"] else None,
             "position": r["pos"]} for r in scored[:limit]]


def _best_bowling(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    figs = [r for r in rows if r["wickets"] is not None and (r["wickets"] or 0) > 0]
    figs.sort(key=lambda r: (-(r["wickets"]), r["runs"] if r["runs"] is not None else 10 ** 6))
    return [{"figures": f"{r['wickets']}-{r['runs'] if r['runs'] is not None else '?'}",
             "wickets": r["wickets"], "runs": r["runs"], "opposition": r["opposition"], "ground": r["ground"],
             "date": r["match_date"].isoformat() if r["match_date"] else None} for r in figs[:limit]]


def _dismissals(rows: list[dict[str, Any]], names: dict[str, str]) -> dict[str, Any]:
    how: dict[str, int] = {}
    by: dict[str, int] = {}
    for r in rows:
        if _is_out(r["dt"]):
            how[r["dt"]] = how.get(r["dt"], 0) + 1
            bowler = r.get("bowler")
            if bowler:
                key = str(bowler)
                by[key] = by.get(key, 0) + 1
    how_out = sorted(({"type": k.replace("_", " "), "count": v} for k, v in how.items()),
                     key=lambda x: -x["count"])
    dismissed_by = sorted(({"player": names.get(k, "Unknown"), "count": v} for k, v in by.items()),
                          key=lambda x: -x["count"])[:15]
    return {"how_out": how_out, "dismissed_by": dismissed_by}


def _scores(rows: list[dict[str, Any]]) -> dict[str, Any]:
    scored = sorted((r for r in rows if r["runs"] is not None),
                    key=lambda r: (r["match_date"] is None, r["match_date"]))
    innings = [{"date": r["match_date"].isoformat() if r["match_date"] else None, "runs": r["runs"],
                "not_out": not _is_out(r["dt"])} for r in scored]
    buckets = ["0-9", "10-19", "20-29", "30-39", "40-49", "50-99", "100+"]
    freq = {b: 0 for b in buckets}
    for r in scored:
        v = r["runs"]
        b = "100+" if v >= 100 else "50-99" if v >= 50 else f"{(v // 10) * 10}-{(v // 10) * 10 + 9}"
        freq[b] = freq.get(b, 0) + 1
    return {"innings": innings, "frequency": [{"range": b, "count": freq[b]} for b in buckets]}


def _partnerships(conn: Connection, workspace_id: UUID, ids: list[str], names: dict[str, str],
                  limit: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(
            "SELECT p.runs, p.wicket_number AS wicket, p.unbroken, p.player1_person_id AS a, "
            " p.player2_person_id AS b, m.match_date, v.name AS ground, "
            " (SELECT coalesce(nullif(o.short_name,''), o.name) FROM match_team mt "
            "  JOIN team t ON t.id = mt.team_id JOIN organisation o ON o.id = t.organisation_id "
            "  WHERE mt.match_id = m.id AND mt.team_id <> i.batting_team_id LIMIT 1) AS opposition "
            "FROM partnership p JOIN innings i ON i.id = p.innings_id JOIN match m ON m.id = i.match_id "
            "LEFT JOIN venue v ON v.id = m.venue_id "
            f"WHERE p.runs IS NOT NULL AND m.workspace_id = :w AND {_APPROVED} "
            "  AND (p.player1_person_id = ANY(CAST(:ids AS uuid[])) "
            "       OR p.player2_person_id = ANY(CAST(:ids AS uuid[]))) "
            "ORDER BY p.runs DESC LIMIT :lim"
        ),
        {"w": workspace_id, "ids": ids, "lim": limit},
    ).mappings().all()
    idset = set(ids)
    out = []
    for r in rows:
        partner_id = str(r["b"]) if str(r["a"]) in idset else str(r["a"])
        out.append({"runs": int(r["runs"]), "unbroken": bool(r["unbroken"]), "wicket": r["wicket"],
                    "partner": names.get(partner_id, "Unknown"), "opposition": r["opposition"],
                    "ground": r["ground"], "date": r["match_date"].isoformat() if r["match_date"] else None})
    return out


def _partnership_totals(conn: Connection, workspace_id: UUID, ids: list[str], names: dict[str, str],
                        limit: int) -> list[dict[str, Any]]:
    """Career aggregate per partner: total partnership runs put on WITH each other player, the number of
    recorded stands together, and the best single stand. Pairs are unordered; approved matches only."""
    rows = conn.execute(
        text(
            "SELECT CASE WHEN p.player1_person_id = ANY(CAST(:ids AS uuid[])) "
            "            THEN p.player2_person_id ELSE p.player1_person_id END AS partner, "
            " sum(p.runs) AS total, count(*) AS stands, max(p.runs) AS best "
            "FROM partnership p JOIN innings i ON i.id = p.innings_id JOIN match m ON m.id = i.match_id "
            f"WHERE p.runs IS NOT NULL AND m.workspace_id = :w AND {_APPROVED} "
            "  AND p.player1_person_id IS NOT NULL AND p.player2_person_id IS NOT NULL "
            "  AND (p.player1_person_id = ANY(CAST(:ids AS uuid[])) "
            "       OR p.player2_person_id = ANY(CAST(:ids AS uuid[]))) "
            "GROUP BY partner ORDER BY total DESC LIMIT :lim"
        ),
        {"w": workspace_id, "ids": ids, "lim": limit},
    ).mappings().all()
    idset = set(ids)
    out = []
    for r in rows:
        pid = str(r["partner"])
        if pid in idset:
            continue                                   # guard against a self-pair row
        out.append({"partner": names.get(pid, "Unknown"), "runs": int(r["total"] or 0),
                    "stands": int(r["stands"]), "best": int(r["best"] or 0)})
    return out


def player_analysis(conn: Connection, workspace_id: UUID, person_id: UUID, *, limit: int = 15) -> dict[str, Any]:
    ids = _merge_ids(conn, person_id)
    names = _names(conn, workspace_id)
    bat = _batting_innings(conn, workspace_id, ids)
    bowl = _bowling_innings(conn, workspace_id, ids)
    dims = ("opposition", "ground", "grade", "format")
    return {
        "splits": {d: {"batting": _split(bat, d, _bat_agg), "bowling": _split(bowl, d, _bowl_agg)} for d in dims},
        "best_batting": _best_batting(bat, limit),
        "best_bowling": _best_bowling(bowl, limit),
        "partnerships": _partnerships(conn, workspace_id, ids, names, limit),
        "partnership_totals": _partnership_totals(conn, workspace_id, ids, names, limit),
        "dismissals": _dismissals(bat, names),
        "scores": _scores(bat),
    }
