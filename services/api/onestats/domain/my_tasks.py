"""Unified "My Tasks" — one task surface across the existing workflows (Part 16).

This does NOT introduce a new task system. It aggregates the work items that already exist:
  * the **verification workflow** — scorecards awaiting approval, and an editor's own drafts;
  * the **Research Centre** — open/in-progress `research_task` rows.
Each item is filtered server-side by the permission needed to act on it, so a user only ever sees
tasks their role can actually progress. Every field comes from real rows; nothing is fabricated.

Must be called inside a workspace transaction (RLS scopes every query to the workspace).
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

# task kind -> (permission required to act, base priority, link the UI opens)
_SOURCES = {
    "approval": ("scorecard.approve", 3, "/matches"),
    "draft": ("match.manage", 1, "/matches"),
    "research": ("research.manage", 2, "/manage/research"),
}


def _match_sides(alias: str = "m") -> str:
    return (
        f"(SELECT t.name FROM match_team mt JOIN team t ON t.id = mt.team_id "
        f" WHERE mt.match_id = {alias}.id AND mt.is_home) AS home_name, "
        f"(SELECT t.name FROM match_team mt JOIN team t ON t.id = mt.team_id "
        f" WHERE mt.match_id = {alias}.id AND NOT mt.is_home) AS away_name"
    )


def _fixture_title(home: str | None, away: str | None, date: Any, rnd: str | None) -> tuple[str, str]:
    title = f"{home} v {away}" if home and away else (home or away or "Scorecard")
    bits = []
    if date is not None:
        bits.append(str(date))
    if rnd:
        bits.append(f"Round {rnd}")
    return title, " · ".join(bits)


def my_tasks(conn: Connection, workspace_id: UUID, perms: set[str], user_id: str,
             *, limit_per_source: int = 25) -> dict[str, Any]:
    tasks: list[dict[str, Any]] = []

    # --- verification workflow: scorecards awaiting approval ---
    if "scorecard.approve" in perms:
        for r in conn.execute(
            text(f"SELECT m.id, m.match_date, m.round, m.submitted_by, m.submitted_at, m.created_at, "
                 f"{_match_sides()} FROM match m WHERE m.approval_status = 'awaiting_approval' "
                 "ORDER BY m.submitted_at DESC NULLS LAST, m.match_date DESC NULLS LAST LIMIT :lim"),
            {"lim": limit_per_source},
        ).mappings():
            title, subtitle = _fixture_title(r["home_name"], r["away_name"], r["match_date"], r["round"])
            # separation-of-duties signal: flag when the approver would also be the submitter
            self_submitted = bool(r["submitted_by"] and str(r["submitted_by"]) == str(user_id))
            tasks.append({
                "id": str(r["id"]), "kind": "approval", "title": title,
                "subtitle": subtitle or "Awaiting approval", "priority": _SOURCES["approval"][1],
                "permission": _SOURCES["approval"][0], "link": _SOURCES["approval"][2],
                "at": (r["submitted_at"] or r["created_at"]).isoformat() if (r["submitted_at"] or r["created_at"]) else None,
                "self_submitted": self_submitted,
            })

    # --- editor's work-in-progress: draft scorecards ---
    if "match.manage" in perms:
        for r in conn.execute(
            text(f"SELECT m.id, m.match_date, m.round, m.created_at, {_match_sides()} "
                 "FROM match m WHERE m.approval_status = 'draft' "
                 "ORDER BY m.match_date DESC NULLS LAST, m.created_at DESC LIMIT :lim"),
            {"lim": limit_per_source},
        ).mappings():
            title, subtitle = _fixture_title(r["home_name"], r["away_name"], r["match_date"], r["round"])
            tasks.append({
                "id": str(r["id"]), "kind": "draft", "title": title,
                "subtitle": subtitle or "Draft scorecard", "priority": _SOURCES["draft"][1],
                "permission": _SOURCES["draft"][0], "link": _SOURCES["draft"][2],
                "at": r["created_at"].isoformat() if r["created_at"] else None,
                "self_submitted": False,
            })

    # --- Research Centre: open / in-progress research tasks ---
    if "research.manage" in perms:
        for r in conn.execute(
            text("SELECT id, title, description, priority, status, assigned_to, created_at "
                 "FROM research_task WHERE status IN ('open','in_progress') "
                 "ORDER BY priority DESC, created_at LIMIT :lim"),
            {"lim": limit_per_source},
        ).mappings():
            tasks.append({
                "id": str(r["id"]), "kind": "research", "title": r["title"],
                "subtitle": (r["description"] or r["status"] or "")[:120],
                "priority": _SOURCES["research"][1] + int(r["priority"] or 0),
                "permission": _SOURCES["research"][0], "link": _SOURCES["research"][2],
                "at": r["created_at"].isoformat() if r["created_at"] else None,
                "self_submitted": False,
            })

    tasks.sort(key=lambda t: (-t["priority"], t["at"] or ""))
    counts = {k: sum(1 for t in tasks if t["kind"] == k) for k in _SOURCES}
    return {"tasks": tasks, "counts": counts, "total": len(tasks)}
