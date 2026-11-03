"""Import a parsed Cricsheet match into the OneStats scorecard tables (Parts F/G).

Takes a :class:`onestats.domain.intl.cricsheet.ParsedMatch` and writes a match, its innings, batting and
bowling onto the existing domain (``matches``/``innings``/``batting``/``bowling``), reusing the identity
model so teams and players are STABLE — never auto-merged. It then registers/links the match-index
entry. Guarantees:

  * Stable identities: a player is resolved by the Cricsheet registry id (stored as a
    ``person_source_identity``) so re-imports and other sources reconcile to the same person; a fallback
    exact-name match is used only when it is unambiguous, otherwise a new person is created and flagged —
    distinct people are never merged. Teams resolve by name/alias; an unknown side is created as a new
    identity, not merged into an existing one.
  * Idempotent re-import: the match carries ``source_system='cricsheet'`` + the Cricsheet id, so a second
    import of the same match UPDATES in place (the previous draft is replaced), never duplicates.
  * Never overwrite verified work: if the existing match is already approved/verified, the import is
    SKIPPED and flagged for human attention — lower-quality data never clobbers a confirmed scorecard.
  * Not auto-counted: the imported match is left UNAPPROVED, so it does not enter official statistics
    until a person verifies it. Nothing here claims completeness.
  * Era-safe figures come from the parser (6- vs 8-ball overs, bowler charges, etc.); this layer only maps.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain import batting, bowling, matches, people
from onestats.domain import innings as inn
from onestats.domain.intl import match_index
from onestats.domain.intl.cricsheet import ParsedBatting, ParsedMatch

SOURCE_SYSTEM = "cricsheet"

# Cricsheet dismissal kind -> OneStats dismissal_type. Anything out but unmapped becomes ``unknown_out``
# (the batter WAS out) with the raw kind kept in dismissal_source_code, so we never assert a wrong type.
_DISMISSAL = {
    "bowled": "bowled", "caught": "caught", "caught and bowled": "caught_and_bowled", "lbw": "lbw",
    "stumped": "stumped", "hit wicket": "hit_wicket", "run out": "run_out",
    "retired hurt": "retired_not_out", "retired not out": "retired_not_out", "retired out": "retired_out",
    "retired - out": "retired_out", "obstructing the field": "obstructing",
    "hit the ball twice": "hit_twice", "timed out": "timed_out",
}
# approved/verified statuses we must never overwrite with a re-import
_PROTECTED = ("approved", "verified")


def _existing_match(conn: Connection, workspace_id: UUID, source_ref: str) -> dict[str, Any] | None:
    r = conn.execute(
        text("SELECT id, approval_status FROM match WHERE workspace_id = :w "
             "AND source_system = :ss AND source_ref = :sr"),
        {"w": workspace_id, "ss": SOURCE_SYSTEM, "sr": source_ref},
    ).mappings().first()
    return dict(r) if r else None


def _resolve_team(conn: Connection, workspace_id: UUID, actor: str, name: str,
                  created: list[str]) -> UUID:
    """Resolve a national side by name (exact, case-insensitive), else create a new identity. Never
    merges into an existing differently-named side."""
    row = conn.execute(
        text("SELECT id FROM team WHERE workspace_id = :w AND lower(name) = lower(:n) "
             "ORDER BY created_at LIMIT 1"),
        {"w": workspace_id, "n": name},
    ).scalar_one_or_none()
    if row is not None:
        return row
    oid = conn.execute(
        text("INSERT INTO organisation(workspace_id, name, kind) VALUES (:w, :n, 'intl_team') RETURNING id"),
        {"w": workspace_id, "n": name},
    ).scalar_one()
    tid = conn.execute(
        text("INSERT INTO team(workspace_id, organisation_id, name, program) "
             "VALUES (:w, :o, :n, 'seniors') RETURNING id"),
        {"w": workspace_id, "o": oid, "n": name},
    ).scalar_one()
    created.append(name)
    return tid


def _resolve_person(conn: Connection, workspace_id: UUID, actor: str, name: str,
                    registry: dict[str, str], created: list[str], name_matched: list[str]) -> UUID:
    """Resolve a player to a stable person id. Preference order: the Cricsheet registry id (a
    cross-source stable key stored as a source identity), then a UNIQUE exact-name match, else a new
    person. Ambiguous names create a new person (flagged) rather than risk merging two people."""
    cid = registry.get(name)
    if cid:
        hit = conn.execute(
            text("SELECT person_id FROM person_source_identity WHERE source_system = :ss AND source_ref = :sr"),
            {"ss": SOURCE_SYSTEM, "sr": cid},
        ).scalar_one_or_none()
        if hit is not None:
            return hit
    # name fallback: only when exactly one person carries that display name
    rows = conn.execute(
        text("SELECT id FROM person WHERE workspace_id = :w AND lower(display_name) = lower(:n) "
             "AND merged_into_id IS NULL"),
        {"w": workspace_id, "n": name},
    ).scalars().all()
    if len(rows) == 1 and not cid:
        name_matched.append(name)
        return rows[0]
    pid = people.create_person(conn, workspace_id, actor, display_name=name)
    created.append(name)
    if cid:
        people.add_source_identity(conn, workspace_id, actor, pid, source_system=SOURCE_SYSTEM,
                                   source_ref=cid, source_display_name=name)
    return pid


def _dismissal(b: ParsedBatting) -> tuple[str, str | None]:
    if not b.out:
        return "not_out", None
    mapped = _DISMISSAL.get((b.dismissal_kind or "").lower())
    return (mapped or "unknown_out"), b.dismissal_kind


def _outcome(parsed: ParsedMatch, team_ids: dict[str, UUID]) -> dict[str, Any] | None:
    o = parsed.outcome or {}
    result = str(o.get("result", "")).lower()
    raw = o.get("method")  # e.g. "D/L" — kept as provenance, never silently applied
    if result == "draw":
        return {"result_type": "draw", "result_raw": raw}
    if result == "tie":
        return {"result_type": "tie", "result_raw": raw}
    if result in ("no result", "no_result"):
        return {"result_type": "no_result", "result_raw": raw}
    winner = o.get("winner")
    if winner and winner in team_ids:
        by = o.get("by", {}) or {}
        rt = "home_win" if parsed.teams and winner == parsed.teams[0] else "away_win"
        return {"result_type": rt, "won_by_team_id": team_ids[winner],
                "margin_runs": by.get("runs"), "margin_wickets": by.get("wickets"), "result_raw": raw}
    return None  # unknown outcome: leave the result unset rather than guess


def import_match(conn: Connection, workspace_id: UUID, actor: str, parsed: ParsedMatch, *,
                 official_status: str = "recognised") -> dict[str, Any]:
    """Import (or re-import) one parsed Cricsheet match. Returns a summary with the match id, whether it
    was created/updated/skipped, identity counts and any warnings."""
    warnings: list[str] = []
    existing = _existing_match(conn, workspace_id, parsed.source_ref)
    if existing is not None and existing["approval_status"] in _PROTECTED:
        return {"status": "skipped_verified", "match_id": str(existing["id"]),
                "reason": "an approved/verified scorecard already exists for this match; "
                          "not overwriting with re-imported data (flagged for review)."}
    if existing is not None:
        # replace the previous (unverified) draft cleanly — cascade clears its innings/entries
        conn.execute(text("DELETE FROM match WHERE id = :id AND workspace_id = :w"),
                     {"id": existing["id"], "w": workspace_id})

    teams_created: list[str] = []
    players_created: list[str] = []
    name_matched: list[str] = []
    team_ids = {name: _resolve_team(conn, workspace_id, actor, name, teams_created)
                for name in parsed.teams}

    mid = matches.create_match(
        conn, workspace_id, actor, match_date=parsed.start_date, format=parsed.format,
        round=(str(parsed.match_number) if parsed.match_number is not None else None),
        source_system=SOURCE_SYSTEM, source_ref=parsed.source_ref)
    # Cricsheet does not record home/away; use positional order and flag it, so the home/away SPLIT is
    # never silently trusted for internationals (the batting/bowling figures are unaffected).
    for i, name in enumerate(parsed.teams):
        matches.set_team(conn, workspace_id, actor, mid, team_id=team_ids[name], is_home=(i == 0))
    if len(parsed.teams) == 2:
        warnings.append("home/away is positional only (not provided by the source)")

    def person(name: str) -> UUID:
        return _resolve_person(conn, workspace_id, actor, name, parsed.registry, players_created, name_matched)

    for n, pi in enumerate(parsed.innings, start=1):
        status = "declared" if pi.declared else "forfeited" if pi.forfeited else "completed"
        iid = inn.create_innings(
            conn, workspace_id, actor, match_id=mid, inns_number=n,
            batting_team_id=team_ids.get(pi.batting_team), bowling_team_id=team_ids.get(pi.bowling_team),
            status=status, byes=pi.extras.get("byes"), legbyes=pi.extras.get("legbyes"),
            wides=pi.extras.get("wides"), noballs=pi.extras.get("noballs"),
            penalty=pi.extras.get("penalty"), source_system=SOURCE_SYSTEM, source_ref=parsed.source_ref)
        for b in pi.batting:
            dtype, draw_code = _dismissal(b)
            batting.create_entry(
                conn, workspace_id, actor, innings_id=iid, person_id=person(b.name),
                batting_position=b.position, runs=b.runs, balls_faced=b.balls_faced,
                fours=b.fours, sixes=b.sixes, dismissal_type=dtype, dismissal_source_code=draw_code,
                bowler_person_id=(person(b.bowler) if b.bowler else None),
                fielder_person_id=(person(b.fielders[0]) if b.fielders else None),
                source_system=SOURCE_SYSTEM, source_ref=parsed.source_ref)
        for bw in pi.bowling:
            bowling.create_entry(
                conn, workspace_id, actor, innings_id=iid, person_id=person(bw.name),
                bowling_order=bw.order, legal_balls=bw.legal_balls, maidens=bw.maidens,
                runs_conceded=bw.runs_conceded, wickets=bw.wickets, wides=bw.wides, noballs=bw.noballs,
                source_system=SOURCE_SYSTEM, source_ref=parsed.source_ref)

    outcome = _outcome(parsed, team_ids)
    if outcome is not None:
        matches.set_result(conn, workspace_id, actor, mid, **outcome)

    # match-index: register this match's external ref and link it (moves the entry to 'imported';
    # link_match is gated so only a 'recognised' entry is importable).
    a, b = (parsed.teams + [None, None])[:2]
    entry = match_index.register(
        conn, workspace_id, actor, format=parsed.format, source_refs={SOURCE_SYSTEM: parsed.source_ref},
        official_status=official_status, start_date=parsed.start_date, team_a=a, team_b=b,
        venue_name=parsed.venue, series=parsed.event_name)
    indexed = False
    if entry["official_status"] == "recognised":
        match_index.link_match(conn, workspace_id, actor, entry["id"], mid)
        indexed = True
    else:
        warnings.append(f"match-index entry is '{entry['official_status']}', not linked (held for review)")

    return {
        "status": "updated" if existing is not None else "created",
        "match_id": str(mid), "index_entry_id": str(entry["id"]), "indexed": indexed,
        "innings": len(parsed.innings),
        "teams_created": teams_created, "players_created": len(players_created),
        "players_name_matched": name_matched, "approved": False, "warnings": warnings,
    }
