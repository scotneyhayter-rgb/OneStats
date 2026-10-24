"""Controlled CricketStatz import into a OneStats workspace (Phase 6, Stage 8 — Sandbox acceptance).

SAFE BY DEFAULT: runs a PREVIEW (stage + validate + preview) inside a transaction that is ROLLED
BACK — nothing is written — unless you pass --commit. --limit caps how many matches are imported so
you can approve a small slice before the full historical dataset. The original JSON is only read,
never modified. Idempotent: re-running --commit on the same data creates no duplicates.

Examples (run from services/api with the project venv):
  python scripts/cs_import.py --file "C:/Users/<you>/Downloads/CS26266_1br2is1nqhk.json" \
      --workspace "Sandbox" --limit 2                 # preview only (no writes)
  python scripts/cs_import.py --file "...CS26266_...json" --workspace "Sandbox" --limit 2 --commit
"""
from __future__ import annotations

import argparse
import json
import sys

from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import imports, people_import

ACTOR = "11111111-1111-1111-1111-111111111111"  # system actor for the import (audited)


def _referenced_player_ids(matches: list, scorecards: dict) -> set[int]:
    ids: set[int] = set()
    for m in matches:
        for k in ("homecaptain1", "homekeeper1", "homekeeper2", "awaycaptain1", "awaykeeper1",
                  "awaykeeper2", "tosswonby", "official1", "official2", "official3",
                  "scorer1", "scorer2", "scorer3"):
            v = m.get(k)
            if v:
                ids.add(v)
    for w in scorecards.get("batting", []):
        for inn in w.get("cricket_Innings") or []:
            for b in inn.get("cricket_batting") or []:
                for k in ("BatsmanID", "Bowler", "Fielder", "FOWBatID"):
                    if b and b.get(k):
                        ids.add(b[k])
    for w in scorecards.get("bowling", []):
        for inn in w.get("cricket_Innings") or []:
            for bw in inn.get("cricket_bowling") or []:
                if bw and bw.get("bowlerID"):
                    ids.add(bw["bowlerID"])
    return ids


def main() -> int:
    ap = argparse.ArgumentParser(description="Controlled CricketStatz import (preview unless --commit).")
    ap.add_argument("--file", required=True, help="Path to the CricketStatz JSON export (read-only).")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--workspace", help="Target workspace name (e.g. Sandbox).")
    g.add_argument("--workspace-id", help="Target workspace UUID.")
    ap.add_argument("--limit", type=int, default=2, help="Max matches to import (default 2).")
    ap.add_argument("--commit", action="store_true", help="Persist the import (default: preview + rollback).")
    args = ap.parse_args()

    s = get_settings()
    if not s.db_configured:
        print("No database configured (ONESTATS_* env).", file=sys.stderr)
        return 2
    with open(args.file, encoding="utf-8-sig") as fh:
        data = json.load(fh)

    matches = data.get("matches", [])[: args.limit]
    keep = {m["MatchID"] for m in matches}
    scard = {c: [w for w in (data.get(c) or []) if w.get("MatchID") in keep]
             for c in ("innings", "batting", "bowling")}
    pids = _referenced_player_ids(matches, scard)
    people_payload = {
        "players": [p for p in (data.get("players") or []) if p.get("PlayerID") in pids],
        "officials": [o for o in (data.get("officials") or []) if o.get("PlayerID") in pids],
    }

    # Scope structural records to ONLY what the selected matches reference — nothing superfluous.
    team_ids = {m.get("HomeTeam") for m in matches} | {m.get("AwayTeam") for m in matches}
    for w in scard["innings"]:
        for inn in w.get("cricket_Innings") or []:
            team_ids |= {inn.get("battingteam"), inn.get("bowlingteam")}
    team_ids -= {0, None}
    grade_ids = {m.get("Grade") for m in matches} - {0, None}
    ground_ids = {m.get("Ground") for m in matches} - {0, None}
    teams = [t for t in (data.get("teams") or []) if t.get("TeamID") in team_ids]
    club_ids = {t.get("ClubID") for t in teams} - {0, None}
    struct_payload = {
        "clubs": [c for c in (data.get("clubs") or []) if c.get("ClubID") in club_ids],
        "teams": teams,
        "venues": [v for v in (data.get("venues") or []) if v.get("GroundID") in ground_ids],
        "divisions": [d for d in (data.get("divisions") or []) if d.get("GradeID") in grade_ids],
        "matches": matches,
    }
    struct_payload.update(scard)
    print(f"slice scope: {len(struct_payload['clubs'])} clubs, {len(teams)} teams, "
          f"{len(struct_payload['venues'])} venues, {len(struct_payload['divisions'])} grades, "
          f"{len(matches)} matches, {len(people_payload['players'])} players")

    eng = create_engine(s.database_url, future=True)
    with eng.connect() as c:
        trans = c.begin()
        try:
            if args.workspace_id:
                wid = args.workspace_id
            else:
                row = c.execute(text("SELECT id FROM workspace WHERE name = :n"), {"n": args.workspace}).first()
                if row is None:
                    print(f"Workspace {args.workspace!r} not found.", file=sys.stderr)
                    return 3
                wid = row[0]
            set_workspace(c, wid)

            # 1) people first (so scorecard player references resolve) — no auto-merge on name
            if people_payload["players"] or people_payload["officials"]:
                pb = people_import.stage_people(c, wid, ACTOR, payload=people_payload)["batch_id"]
                people_import.detect(c, wid, ACTOR, pb)
                ppl = people_import.promote(c, wid, ACTOR, pb)
                print("people:", ppl.get("created", ppl))

            # 2) structural + scorecards
            bid = imports.parse_and_stage(c, wid, ACTOR, payload=struct_payload,
                                          filename=args.file.rsplit("/", 1)[-1])["batch_id"]
            imports.validate_batch(c, wid, ACTOR, bid)
            prev = imports.preview_batch(c, bid)
            print("preview:", {k: prev[k] for k in ("promotable_now", "unresolved", "matches_promotable")})

            hr = imports.unresolved_howout_report(struct_payload)
            print("unresolved howout codes (this slice):",
                  {c2["code"]: c2["count"] for c2 in hr["unresolved_codes"]})

            if args.commit:
                res = imports.promote_batch(c, wid, ACTOR, bid)
                print("PROMOTED:", {k: v for k, v in res["created"].items() if v},
                      "| matched:", {k: v for k, v in res["matched"].items() if v})
                trans.commit()
                print("COMMITTED to workspace", wid)
            else:
                trans.rollback()
                print("PREVIEW ONLY — rolled back, nothing written. Re-run with --commit to persist.")
        except Exception:
            trans.rollback()
            raise
    eng.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
