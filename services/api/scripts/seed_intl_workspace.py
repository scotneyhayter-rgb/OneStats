"""Create (or re-sync) the "International Men's Cricket" workspace — idempotent and safe.

This is the Part B / identity foundation: it creates ONE clearly-named workspace of type
``international`` covering the three officially recognised men's international formats, enables exactly
those formats, seeds the full-member national sides as stable team identities, and registers the
recurring daily 04:00 Australia/Melbourne update task. It is fully idempotent — re-running it never
duplicates the workspace, an organisation, a team or the scheduled task — and it touches ONLY this one
workspace, never any other workspace's data.

It does NOT import any match or scorecard and makes NO claim about historical completeness: the match
index starts empty, and the daily task truthfully records that the import pipeline is not yet wired
(see onestats.domain.intl.dispatch).

Usage (from services/api, with the venv python):
    .venv\\Scripts\\python scripts\\seed_intl_workspace.py            # create / re-sync
    .venv\\Scripts\\python scripts\\seed_intl_workspace.py --teardown  # remove ONLY this workspace
"""
from __future__ import annotations

import datetime as dt
import sys

from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import match_formats
from onestats.domain.intl import dispatch as intl_dispatch
from onestats.domain.scheduler import tasks

WS_NAME = "International Men's Cricket"
WS_SHORT = "intl-mens"
ENABLED_FORMATS = {"test", "odi", "t20i"}

# The 12 full-member men's Test nations — unambiguous, stable identities. Associate members (T20I)
# are NOT pre-seeded: they are created as research candidates during import and resolved to identities
# then, so we never invent or auto-merge sides. (name, short).
FULL_MEMBERS = [
    ("Australia", "AUS"), ("England", "ENG"), ("South Africa", "RSA"), ("West Indies", "WI"),
    ("New Zealand", "NZ"), ("India", "IND"), ("Pakistan", "PAK"), ("Sri Lanka", "SL"),
    ("Zimbabwe", "ZIM"), ("Bangladesh", "BAN"), ("Ireland", "IRE"), ("Afghanistan", "AFG"),
]

# Established historical names of the SAME national team (a rename, not a different entity). Only
# well-documented, non-controversial cases are seeded; anything unclear is left for research.
NAME_HISTORY = {
    # Sri Lanka toured and was recorded as "Ceylon" until it was renamed in 1972.
    "Sri Lanka": [("Ceylon", None, dt.date(1972, 5, 22))],
}

ACTOR_SUPER_ADMIN_FALLBACK = "00000000-0000-0000-0000-000000000000"


def _actor(conn) -> str:
    """Attribute seeding to the real Super Administrator where one exists (actions are the user's),
    else a clearly labelled system actor."""
    row = conn.execute(
        text("SELECT id FROM app_user WHERE is_super_admin = true ORDER BY created_at LIMIT 1")
    ).scalar_one_or_none()
    return str(row) if row else ACTOR_SUPER_ADMIN_FALLBACK


def _workspace_id(conn) -> str | None:
    return conn.execute(text("SELECT id FROM workspace WHERE name = :n"), {"n": WS_NAME}).scalar_one_or_none()


def _teardown(su) -> int:
    removed = 0
    with su.connect() as c:
        ids = list(c.execute(text("SELECT id FROM workspace WHERE name = :n"), {"n": WS_NAME}).scalars())
    for wid in ids:
        with su.connect() as c:
            t = c.begin()
            set_workspace(c, wid)
            c.execute(text("DELETE FROM audit_log WHERE workspace_id = :w"), {"w": wid})
            c.execute(text("DELETE FROM workspace WHERE id = :w"), {"w": wid})  # CASCADE clears the rest
            t.commit()
            removed += 1
    return removed


def _ensure_org(conn, wid, actor, name, short) -> str:
    oid = conn.execute(
        text("SELECT id FROM organisation WHERE workspace_id = :w AND name = :n"),
        {"w": wid, "n": name},
    ).scalar_one_or_none()
    if oid is not None:
        return str(oid)
    oid = conn.execute(
        text("INSERT INTO organisation(workspace_id, name, short_name, kind) "
             "VALUES (:w, :n, :s, 'intl_team') RETURNING id"),
        {"w": wid, "n": name, "s": short},
    ).scalar_one()
    return str(oid)


def _ensure_team(conn, wid, org_id, name) -> str:
    tid = conn.execute(
        text("SELECT id FROM team WHERE workspace_id = :w AND organisation_id = :o AND name = :n"),
        {"w": wid, "o": org_id, "n": name},
    ).scalar_one_or_none()
    if tid is not None:
        return str(tid)
    return str(conn.execute(
        text("INSERT INTO team(workspace_id, organisation_id, name, program) "
             "VALUES (:w, :o, :n, 'seniors') RETURNING id"),
        {"w": wid, "o": org_id, "n": name},
    ).scalar_one())


def _ensure_name_history(conn, wid, team_id, name, valid_from, valid_to) -> None:
    exists = conn.execute(
        text("SELECT 1 FROM team_name_history WHERE workspace_id = :w AND team_id = :t AND name = :n"),
        {"w": wid, "t": team_id, "n": name},
    ).first()
    if exists:
        return
    conn.execute(
        text("INSERT INTO team_name_history(workspace_id, team_id, name, valid_from, valid_to) "
             "VALUES (:w, :t, :n, :vf, :vt)"),
        {"w": wid, "t": team_id, "n": name, "vf": valid_from, "vt": valid_to},
    )


def _ensure_alias(conn, wid, team_id, alias) -> None:
    conn.execute(
        text("INSERT INTO research_alias(workspace_id, entity_type, entity_id, alias, normalised, "
             "alias_kind) VALUES (:w, 'team', :t, :a, :norm, 'former_name') "
             "ON CONFLICT ON CONSTRAINT uq_research_alias DO NOTHING"),
        {"w": wid, "t": team_id, "a": alias, "norm": alias.strip().lower()},
    )


def _sync(app) -> dict:
    intl_dispatch.register()
    with app.connect() as c:
        t = c.begin()
        actor = _actor(c)
        wid = _workspace_id(c)
        created = wid is None
        if created:
            wid = c.execute(
                text("INSERT INTO workspace(name, short_name, type) VALUES (:n, :s, 'international') "
                     "RETURNING id"),
                {"n": WS_NAME, "s": WS_SHORT},
            ).scalar_one()
        set_workspace(c, wid)

        # formats: enable exactly Test / ODI / T20I, disable the rest (never deletes — matches keep
        # their free-text format regardless).
        for f in match_formats.list_formats(c, wid):
            want = f["code"] in ENABLED_FORMATS
            if f["enabled"] != want:
                match_formats.set_enabled(c, wid, actor, f["id"], want)

        # national-team identities
        team_ids: dict[str, str] = {}
        for name, short in FULL_MEMBERS:
            oid = _ensure_org(c, wid, actor, name, short)
            tid = _ensure_team(c, wid, oid, name)
            team_ids[name] = tid
            for hist_name, vf, vt in NAME_HISTORY.get(name, []):
                _ensure_name_history(c, wid, tid, hist_name, vf, vt)
                _ensure_alias(c, wid, tid, hist_name)

        # recurring DAILY 04:00 Australia/Melbourne update (DST-safe, catch-up on). If the existing
        # task was weekly, this switches it to daily and recomputes next_run_at (history preserved).
        task = tasks.upsert_daily(
            c, wid, actor, name="Daily international update", task_kind=intl_dispatch.TASK_KIND,
            tz="Australia/Melbourne", hour=4, minute=0, catch_up=True,
        )
        t.commit()
        return {"workspace_id": str(wid), "created": created, "teams": len(team_ids),
                "next_run_at_utc": task["next_run_at"].isoformat() if task["next_run_at"] else None}


def main() -> int:
    s = get_settings()
    if not s.db_configured:
        print("No database configured — set credentials first.")
        return 1
    app = create_engine(s.database_url, future=True)
    su = create_engine(s.migration_url, future=True)
    try:
        if "--teardown" in sys.argv:
            n = _teardown(su)
            print(f"Removed {n} workspace(s) named {WS_NAME!r}.")
            return 0
        info = _sync(app)
        print(f"{'Created' if info['created'] else 'Re-synced'} workspace {WS_NAME!r}:")
        for k, v in info.items():
            print(f"  {k}: {v}")
        print("\nNo matches imported; the match index is empty and no completeness is claimed.")
        print("The daily task is registered; it will truthfully record 'no_pipeline' until the "
              "research-engine import is wired.")
        return 0
    finally:
        app.dispose()
        su.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
