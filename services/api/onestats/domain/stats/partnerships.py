"""Partnership statistics (Phase 12, Stages 12.8/12.9).

Batting partnerships come from the Phase 7 automatic partnership data (recorded or FoW-derived — no
manual "calculate" step, nothing fabricated). Bowling partnership groups use the user-confirmed D12
method (25-partnership-calculation.md §25.3): a group of 2/3/4 players who appeared in the same match;
for each match where EVERY member participated, sum the bowler-credited wickets of the members (run outs
excluded), count each match once, and aggregate across qualifying matches. Incomplete historical bowling
figures make a group total a known-minimum, never a confirmed zero.
"""
from __future__ import annotations

from itertools import combinations
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain.stats.engine import _where


# ---- batting partnerships -----------------------------------------------------------------------
def batting_partnerships(conn: Connection, filters: dict[str, Any], *, by_wicket: bool = False,
                         limit: int = 50) -> list[dict[str, Any]]:
    """Highest batting partnerships (optionally the best for each wicket) from recorded/FoW-derived
    partnership rows of approved, statistics-eligible matches. Pairs are unordered; unknown runs excluded."""
    # only approved, statistics-eligible matches contribute (match the ledger's official set)
    base = (
        "SELECT p.id, p.wicket_number, p.runs, p.unbroken, p.player1_person_id AS a, p.player2_person_id AS b, "
        " i.match_id, m.match_date "
        "FROM partnership p JOIN innings i ON i.id = p.innings_id JOIN match m ON m.id = i.match_id "
        "WHERE p.runs IS NOT NULL AND m.approval_status IN ('approved','verified_partial') "
        "AND m.include_in_statistics = true AND m.workspace_id = :w"
    )
    params = {"w": filters["workspace_id"]}
    for key, col in (("season_id", "m.season_id"), ("grade_id", "m.grade_id"),
                     ("competition_id", "m.competition_id")):
        if filters.get(key):
            base += f" AND {col} = :{key}"
            params[key] = filters[key]
    # club lens: restrict to partnerships made for one of the selected club's teams
    if filters.get("organisation_id"):
        base += " AND i.batting_team_id IN (SELECT id FROM team WHERE organisation_id = :organisation_id)"
        params["organisation_id"] = filters["organisation_id"]
    rows = conn.execute(text(base), params).mappings().all()
    out = [{"partnership_id": str(r["id"]), "wicket": r["wicket_number"], "runs": int(r["runs"]),
            "unbroken": r["unbroken"], "batter1": str(r["a"]) if r["a"] else None,
            "batter2": str(r["b"]) if r["b"] else None, "match_id": str(r["match_id"]),
            "match_date": r["match_date"].isoformat() if r["match_date"] else None} for r in rows]
    if by_wicket:
        best: dict[Any, dict[str, Any]] = {}
        for r in out:
            w = r["wicket"]
            if w is not None and (w not in best or r["runs"] > best[w]["runs"]):
                best[w] = r
        return [best[w] for w in sorted(best)]
    out.sort(key=lambda r: -r["runs"])
    return out[:limit]


# ---- bowling partnership groups (D12) -----------------------------------------------------------
def bowling_groups(conn: Connection, filters: dict[str, Any], *, size: int = 2, limit: int = 50,
                   max_candidates: int = 40) -> dict[str, Any]:
    """Rank 2/3/4-player bowling groups by combined wickets taken in matches they all played. To stay
    efficient on large datasets, candidates are the top ``max_candidates`` wicket-takers in scope (the
    report notes when the candidate set was capped)."""
    if size not in (2, 3, 4):
        raise ValueError("invalid_group_size")
    where, params = _where(filters)

    # per (person, match) bowler-credited wickets + an incomplete-figures flag, in scope
    wk_rows = conn.execute(
        text(f"SELECT c.subject_id AS pid, c.match_id, (c.metrics->>'wickets')::int AS w, "
             f"((c.metrics->>'balls_known')::int < (c.metrics->>'innings')::int) AS incomplete "
             f"FROM match_stat_contribution c JOIN match m ON m.id = c.match_id "
             f"WHERE c.calculator = 'player_bowling' AND {where}"), params).mappings().all()
    # participation (appeared) per (person, match) in scope
    ap_rows = conn.execute(
        text(f"SELECT c.subject_id AS pid, c.match_id FROM match_stat_contribution c "
             f"JOIN match m ON m.id = c.match_id WHERE c.calculator = 'player_appearance' AND {where}"),
        params).mappings().all()

    appeared: dict[str, set] = {}
    for r in ap_rows:
        appeared.setdefault(str(r["pid"]), set()).add(str(r["match_id"]))
    wkts: dict[tuple, int] = {}
    incomplete_matches: set = set()
    total_wk: dict[str, int] = {}
    for r in wk_rows:
        pid, mid = str(r["pid"]), str(r["match_id"])
        wkts[(pid, mid)] = int(r["w"] or 0)
        total_wk[pid] = total_wk.get(pid, 0) + int(r["w"] or 0)
        if r["incomplete"]:
            incomplete_matches.add((pid, mid))

    # candidates: top wicket-takers (a group only matters if members actually take wickets)
    candidates = sorted(total_wk, key=lambda p: -total_wk[p])
    capped = len(candidates) > max_candidates
    candidates = candidates[:max_candidates]

    groups = []
    for combo in combinations(candidates, size):
        qualifying = set.intersection(*[appeared.get(p, set()) for p in combo]) if all(p in appeared for p in combo) else set()
        if not qualifying:
            continue
        total = 0
        known_min = False
        for m in qualifying:
            for p in combo:
                total += wkts.get((p, m), 0)
                if (p, m) in incomplete_matches:
                    known_min = True
        groups.append({"members": list(combo), "total_wickets": total, "matches_together": len(qualifying),
                       "avg_per_match": round(total / len(qualifying), 2) if qualifying else None,
                       "known_minimum": known_min})
    groups.sort(key=lambda g: -g["total_wickets"])
    return {"size": size, "groups": groups[:limit], "candidates_capped": capped,
            "note": "Same-match bowling group: combined bowler-credited wickets in matches all members "
                    "played (run outs excluded). Not a consecutive-over partnership."}
