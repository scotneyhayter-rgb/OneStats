"""Achievement badges (Phase 13, Stage 13.6).

Badges for a player, clearly distinguishing three sources: automatically-calculated statistical
achievements (from approved records), administrator-confirmed honours, and historical/honorary
recognition. A manually-assigned honour is never presented as an automatically-calculated statistical
record. Calculated badges carry the milestone state (confirmed / known-minimum) so nothing is asserted
beyond the evidence.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.engine import Connection

from onestats.domain.records import honours, milestones
from onestats.domain.stats import engine

_HONOUR_SOURCE = {"life_member": "honorary", "honorary_member": "honorary", "historical_figure": "historical"}


def person_badges(conn: Connection, workspace_id: UUID, person_id: UUID) -> dict[str, Any]:
    f = {"workspace_id": workspace_id}
    calculated: list[dict[str, Any]] = []

    ms = milestones.person_milestones(conn, workspace_id, person_id)
    for metric, data in ms["metrics"].items():
        for m in data["milestones"]:
            if m["state"] in ("achieved_confirmed", "achieved_known_minimum"):
                calculated.append({"label": f"{m['threshold']} {data['label'].lower()}",
                                   "category": metric, "source": "calculated", "state": m["state"]})

    bat = engine.person_batting(conn, f, person_id)
    bowl = engine.person_bowling(conn, f, person_id)
    if int(bat.get("hundreds", 0)) > 0:
        calculated.append({"label": f"{bat['hundreds']}× Century", "category": "batting",
                           "source": "calculated", "state": "achieved_confirmed"})
    if int(bowl.get("five_wkt_innings", 0)) > 0:
        calculated.append({"label": f"{bowl['five_wkt_innings']}× Five-Wicket Innings", "category": "bowling",
                           "source": "calculated", "state": "achieved_confirmed"})

    confirmed: list[dict[str, Any]] = []
    for h in honours.list_honours(conn, workspace_id, person_id=person_id):
        confirmed.append({"label": h["title"], "category": h["honour_type"],
                          "source": _HONOUR_SOURCE.get(h["honour_type"], "confirmed"),
                          "status": h["status"]})

    return {"person_id": str(person_id), "calculated": calculated, "awarded": confirmed,
            "note": "Calculated badges come from approved statistics (state shown). Awarded badges are "
                    "explicitly recorded honours, never inferred from statistics."}
