"""Career milestones (Phase 13, Stage 13.5/13.14).

Compares a person's engine totals to workspace-configurable thresholds and assigns a state
(achieved-confirmed / achieved-known-minimum / upcoming / indeterminate). Runs and wickets carry a
known-minimum flag from the engine (unknown figures are never treated as zero), so a milestone is only
'confirmed' when the confirmed total meets it. Nothing is invented.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.engine import Connection

from onestats.domain.stats import engine

# RMCC-proposed defaults (configurable per workspace; see 26-milestones-and-achievements.md).
DEFAULT_THRESHOLDS: dict[str, list[int]] = {
    "runs": [100, 500, 1000, 2500, 5000, 10000],
    "wickets": [10, 50, 100, 200, 300],
    "matches": [25, 50, 100, 150, 200, 250, 300],
    "catches": [25, 50, 100],
    "stumpings": [10, 25, 50],
    "captaincy_matches": [25, 50, 100],
    "captaincy_wins": [25, 50, 100],
}

_LABELS = {"runs": "Career runs", "wickets": "Career wickets", "matches": "Matches played",
           "catches": "Catches", "stumpings": "Stumpings", "captaincy_matches": "Matches captained",
           "captaincy_wins": "Wins as captain"}


def _states(total: int, known_min: bool, thresholds: list[int], window: int) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    achieved: list[dict[str, Any]] = []
    nxt: dict[str, Any] | None = None
    for t in sorted(thresholds):
        if total >= t:
            achieved.append({"threshold": t, "state": "achieved_known_minimum" if known_min else "achieved_confirmed"})
            continue
        gap = t - total
        if known_min:
            # a known-minimum total below the threshold cannot be confirmed as not-reached
            achieved.append({"threshold": t, "state": "indeterminate"})
        elif gap <= window:
            achieved.append({"threshold": t, "state": "upcoming", "to_go": gap})
        nxt = {"threshold": t, "to_go": gap, "known_minimum": known_min}
        break
    return achieved, nxt


def person_milestones(conn: Connection, workspace_id: UUID, person_id: UUID, *, window: int = 5,
                      thresholds: dict[str, list[int]] | None = None) -> dict[str, Any]:
    th = thresholds or DEFAULT_THRESHOLDS
    f = {"workspace_id": workspace_id}
    bat = engine.person_batting(conn, f, person_id)
    bowl = engine.person_bowling(conn, f, person_id)
    field = engine.person_fielding(conn, f, person_id)
    part = engine.person_participation(conn, f, person_id)
    capt = engine.person_captaincy(conn, f, person_id)

    totals = {
        "runs": (int(bat.get("runs", 0)), bool(bat.get("runs_known_minimum"))),
        "wickets": (int(bowl.get("wickets", 0)), bool(bowl.get("wickets_known_minimum"))),
        "matches": (int(part.get("matches", 0)), False),
        "catches": (int(field.get("catches", 0)), False),
        "stumpings": (int(field.get("stumpings", 0)), False),
        "captaincy_matches": (int(capt.get("captained", 0)), False),
        "captaincy_wins": (int(capt.get("wins", 0)), False),
    }
    out: dict[str, Any] = {"person_id": str(person_id), "metrics": {}}
    for metric, (total, known_min) in totals.items():
        achieved, nxt = _states(total, known_min, th.get(metric, []), window)
        out["metrics"][metric] = {"label": _LABELS[metric], "total": total, "known_minimum": known_min,
                                  "milestones": achieved, "next": nxt}
    return out


def upcoming_for_workspace(conn: Connection, workspace_id: UUID, *, window: int = 10,
                           thresholds: dict[str, list[int]] | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """Players within ``window`` of their next runs/wickets/matches milestone — from confirmed totals
    only (a known-minimum total never drives a misleading prediction)."""
    th = thresholds or DEFAULT_THRESHOLDS
    f = {"workspace_id": workspace_id}
    out: list[dict[str, Any]] = []
    bat = {r["subject_id"]: r for r in engine.batting_leaders(conn, f, limit=1000)}
    bowl = {r["subject_id"]: r for r in engine.bowling_leaders(conn, f, limit=1000)}
    part = {r["subject_id"]: r for r in engine.participation_leaders(conn, f, limit=1000)}
    for metric, source, total_key, km_key in (("runs", bat, "runs", "runs_known_minimum"),
                                              ("wickets", bowl, "wickets", "wickets_known_minimum"),
                                              ("matches", part, "matches", None)):
        for pid, r in source.items():
            if km_key and r.get(km_key):
                continue  # don't predict from incomplete totals
            total = int(r.get(total_key, 0))
            for t in sorted(th.get(metric, [])):
                if total < t:
                    if t - total <= window:
                        out.append({"person_id": pid, "metric": metric, "threshold": t,
                                    "current": total, "to_go": t - total})
                    break
    out.sort(key=lambda x: x["to_go"])
    return out[:limit]
