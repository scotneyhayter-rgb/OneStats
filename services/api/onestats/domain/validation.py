"""Match-level validation aggregation (Phase 7, Stage 7.1).

Gathers the existing advisory warnings from every part of a match's scorecard — batting, bowling,
innings totals/extras/wickets, fall of wickets, partnerships — plus the match result and season
checks, each tagged with the innings and area it belongs to. These are **advisory**: incomplete
historical scorecards remain valid records and are never rejected; the warnings flag discrepancies
for review (relevant innings, area and reason). Reuses each domain's own ``validation_warnings`` and
the result/season checks — it does not re-implement them.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.engine import Connection

from onestats.domain import batting, bowling, partnerships, results, seasons
from onestats.domain import innings as innings_domain


def match_validation(conn: Connection, match_id: UUID) -> list[dict[str, Any]]:
    """Every advisory warning for a match, tagged with scope (innings or match) and area."""
    out: list[dict[str, Any]] = []
    for inn in innings_domain.list_innings(conn, match_id):
        scope = f"Innings {inn['inns_number']}"
        iid = inn["id"]
        for area, fn in (("batting", batting.validation_warnings),
                         ("bowling", bowling.validation_warnings),
                         ("innings", innings_domain.validation_warnings),
                         ("partnerships", partnerships.validation_warnings)):
            for code in fn(conn, iid):
                out.append({"scope": scope, "area": area, "code": code})
    for code in results.result_warnings(conn, match_id):
        out.append({"scope": "Match", "area": "result", "code": code})
    for code in seasons.season_warnings(conn, match_id):
        out.append({"scope": "Match", "area": "season", "code": code})
    return out
