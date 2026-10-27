"""Cricket Statz structural import (Phase 4, Stage 6).

A staging-first pipeline: source rows are parsed verbatim into ``import_staging_record`` under
an ``import_batch`` (source IDs + provenance preserved), validated for referential integrity,
previewed, and only **promoted** into the canonical Phase 1-5 tables on explicit administrator
approval. Promotion is **idempotent** (keyed on source_ref — re-import never duplicates),
**reversible** (``rollback_batch`` removes exactly the canonical rows this batch created), and
**audited**. Nothing is silently discarded.

Scope (evidence-verified structural mappings only — D32/D35, deliverable 16a):

* ``clubs`` → organisation (kind=club), ``teams`` → team (+ organisation link), ``venues`` →
  venue, ``divisions`` → grade (A/B/C Grade confident; others left **unresolved**) under a
  single import competition container.
* ``matches`` are staged **structurally only** and are **not promoted** — there is no canonical
  match table yet (scorecards are Phase 8). Their finals classification is derived only as a
  low-confidence hint and kept **unresolved**; Result codes 3/4/8/9 stay **unresolved**.

No batting/bowling/fielding/scorecards. No auto-merge by name (identity resolution stays an
administrator decision). Unknown ≠ zero throughout (sentinels map to unknown).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain import (
    audit,
    batting,
    bowling,
    competitions,
    innings,
    match_sources,
    matches,
    organisations,
    partnerships,
    teams,
    venues,
)

SOURCE_SYSTEM = "cricket_statz"
_IMPORT_COMP_REF = "cricket_statz:import"

# CricketStatz ``Howout`` dismissal-code legend -> OneStats dismissal_type. Source: the official
# CricketStatz API documentation (cricketstatz.com/api-for-uploading-matches), corroborated by the
# structural evidence in the export (bowler/fielder presence per code) and prior OneStats fixtures.
# See docs/45-cricketstatz-howout-legend.md. ONLY verified codes are mapped; the raw code is always
# preserved in ``dismissal_source_code``, and any code NOT in this table stays UNRESOLVED (NULL) for
# administrator review — nothing is guessed. ``did not bat`` is a non-wicket, never a dismissal.
CS_HOWOUT: dict[int, str] = {
    0: "dnb",               # did not bat — NON-wicket (never a dismissal)
    1: "not_out",           # NON-wicket
    2: "bowled",
    3: "caught",            # caught by a fielder
    6: "lbw",
    7: "run_out",           # credits no bowler
    8: "stumped",
    20: "retired_not_out",  # retired (hurt/ill) — NON-wicket; distinct from retired out
    21: "absent",           # NON-wicket
    22: "retired_out",      # retired out — a genuine dismissal (counts as a wicket)
    # Documented but NOT yet approved -> left UNRESOLVED (NULL): 4 c&b, 5 ct behind, 9 hit wkt,
    # 10 obstructed, 12 hit twice, 23 timed out. Code 11 (handled ball) has no exact OneStats type;
    # code 24 is undocumented. All of these keep their raw code and await confirmation.
}


def map_howout(code: Any) -> str | None:
    """OneStats dismissal_type for a CricketStatz Howout code, or None when the code is not in the
    verified legend (left unresolved — never guessed). Non-integer/blank codes are unresolved too."""
    try:
        return CS_HOWOUT.get(int(code))
    except (TypeError, ValueError):
        return None

# Confirmed by cross-reference (16a.14 / 16a.9).
MATCHTYPE_LABELS = {1: "1 innings per side", 2: "2 innings per side", 3: "T20"}
# Only 0/1/2 are evidence-confirmed; 3/4/8/9 must stay unresolved (never guessed).
RESULT_LABELS = {0: "unknown", 1: "home_win", 2: "away_win"}
# Grade names safe to promote directly; anything else is left unresolved for admin review.
CONFIDENT_GRADES = {"a grade", "b grade", "c grade"}


# --------------------------------------------------------------------------- helpers


def _sha256(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def _round_classification_hint(round_label: str) -> str:
    """A *low-confidence* hint only — never authoritative (user rule, D32). Classification is
    always stored as unresolved for human confirmation."""
    r = (round_label or "").strip().lower()
    if r in ("gf", "gf1", "gf2", "grand final"):
        return "grand_final?"
    if r in ("sf", "semi", "semi final", "semifinal"):
        return "final?"
    if r.isdigit():
        return "home_away?"
    return "unknown"


def get_batch(conn: Connection, batch_id: UUID) -> dict[str, Any] | None:
    r = conn.execute(
        text(
            "SELECT id, source_system, source_filename, source_sha256, status, counts, notes, "
            "created_by, created_at, promoted_at, promoted_by FROM import_batch WHERE id = :id"
        ),
        {"id": batch_id},
    ).mappings().first()
    return dict(r) if r else None


def list_batches(conn: Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(
            "SELECT id, source_system, source_filename, status, counts, created_at, promoted_at "
            "FROM import_batch ORDER BY created_at DESC"
        )
    ).mappings().all()
    return [dict(r) for r in rows]


def list_records(
    conn: Connection, batch_id: UUID, *, entity_type: str | None = None, status: str | None = None
) -> list[dict[str, Any]]:
    sql = (
        "SELECT id, entity_type, source_ref, raw, normalised, status, resolution, "
        "matched_canonical_id, issues FROM import_staging_record WHERE batch_id = :b"
    )
    params: dict[str, Any] = {"b": batch_id}
    if entity_type:
        sql += " AND entity_type = :et"
        params["et"] = entity_type
    if status:
        sql += " AND status = :st"
        params["st"] = status
    sql += " ORDER BY entity_type, source_ref"
    return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]


def _staged(conn: Connection, batch_id: UUID, entity_type: str) -> list[dict[str, Any]]:
    return list_records(conn, batch_id, entity_type=entity_type)


def _insert_record(
    conn: Connection, wid: UUID, batch_id: UUID, entity_type: str, source_ref: str,
    raw: Any, normalised: dict[str, Any], *, status: str = "staged",
    resolution: str | None = None, issues: list[str] | None = None,
) -> None:
    # ON CONFLICT DO NOTHING: duplicate source rows (e.g. a mirrored grand final) are collapsed
    # on (batch, entity_type, source_ref) rather than erroring — nothing is discarded silently
    # beyond an exact in-batch duplicate of the same source id.
    conn.execute(
        text(
            "INSERT INTO import_staging_record"
            "(workspace_id, batch_id, entity_type, source_ref, raw, normalised, status, resolution, issues) "
            "VALUES (:w, :b, :et, :sr, CAST(:raw AS jsonb), CAST(:norm AS jsonb), :st, :res, CAST(:iss AS jsonb)) "
            "ON CONFLICT ON CONSTRAINT uq_staging_record DO NOTHING"
        ),
        {
            "w": wid, "b": batch_id, "et": entity_type, "sr": str(source_ref),
            "raw": json.dumps(raw, default=str), "norm": json.dumps(normalised, default=str),
            "st": status, "res": resolution,
            "iss": json.dumps(issues) if issues else None,
        },
    )


# --------------------------------------------------------------------------- stage


def parse_and_stage(
    conn: Connection, workspace_id: UUID, actor: str, *, payload: dict[str, Any], filename: str | None = None
) -> dict[str, Any]:
    """Validate the source payload and stage every row verbatim. No canonical write occurs."""
    if not isinstance(payload, dict):
        raise ValueError("invalid_payload")  # noqa: TRY004 — uniform ValueError→422 handling
    known = ("clubs", "teams", "venues", "divisions", "matches", "innings", "batting", "bowling")
    if not any(k in payload and payload[k] for k in known):
        raise ValueError("no_importable_collections")

    batch_id = conn.execute(
        text(
            "INSERT INTO import_batch(workspace_id, source_system, source_filename, source_sha256, created_by) "
            "VALUES (:w, :ss, :fn, :sha, :actor) RETURNING id"
        ),
        {"w": workspace_id, "ss": SOURCE_SYSTEM, "fn": filename, "sha": _sha256(payload), "actor": actor},
    ).scalar_one()

    counts: dict[str, int] = {}

    for row in payload.get("clubs") or []:
        ref = row.get("ClubID")
        if ref is None:
            continue
        _insert_record(conn, workspace_id, batch_id, "club", ref, row,
                       {"name": row.get("Name"), "kind": "club"}, resolution="new")
    counts["club"] = len(payload.get("clubs") or [])

    for row in payload.get("venues") or []:
        ref = row.get("GroundID")
        if ref is None:
            continue
        unknown = row.get("Name") == "?"
        _insert_record(conn, workspace_id, batch_id, "venue", ref, row,
                       {"name": None if unknown else row.get("Name"), "unknown_name": unknown},
                       resolution="new")
    counts["venue"] = len(payload.get("venues") or [])

    for row in payload.get("divisions") or []:
        ref = row.get("GradeID")
        if ref is None:
            continue
        name = row.get("Name") or ""
        confident = name.strip().lower() in CONFIDENT_GRADES
        _insert_record(
            conn, workspace_id, batch_id, "division", ref, row,
            {"name": name, "confident": confident},
            status="staged" if confident else "unresolved",
            resolution="new" if confident else "unresolved",
            issues=None if confident else ["ambiguous_grade: preserve original; admin must resolve"],
        )
    counts["division"] = len(payload.get("divisions") or [])

    for row in payload.get("teams") or []:
        ref = row.get("TeamID")
        if ref is None:
            continue
        _insert_record(conn, workspace_id, batch_id, "team", ref, row,
                       {"name": row.get("Name"), "club_source_ref": _s(row.get("ClubID"))},
                       resolution="new")
    counts["team"] = len(payload.get("teams") or [])

    # Intra-club / one-sided matches: the source listed the same team on both sides. Stage a distinct,
    # flagged opponent side per such match so the fixture imports as a valid two-team match (a team can
    # never bat against itself). Reviewable and mergeable later in Teams — never auto-merged.
    opponents = _intra_club_opponents(payload)
    for info in opponents.values():
        _insert_record(
            conn, workspace_id, batch_id, "team", info["ref"],
            {"synthetic_opponent_of": info["orig_ref"]},
            {"name": info["name"], "club_source_ref": info["club_ref"]},
            resolution="new",
            issues=["intra_club_opponent: the source listed the same team on both sides; this distinct "
                    "opponent side was created so the match imports — rename or merge to the correct side"],
        )
    counts["team"] += len(opponents)

    for row in payload.get("matches") or []:
        ref = row.get("MatchID")
        if ref is None:
            continue
        result = row.get("Result")
        result_known = result in RESULT_LABELS
        issues: list[str] = []
        if not result_known:
            issues.append(f"result_unresolved: code {result} not evidence-verified")
        # Classification is ALWAYS 'unclassified'/unverified at import — the round label is a
        # non-authoritative hint only, and a missing classification is never Home & Away.
        issues.append("classification_unresolved: round is a hint only; admin must classify")
        opp = opponents.get(_s(ref))
        if opp is not None:
            issues.append("intra_club_match: home and away were the same source team; a distinct "
                          "opponent side was created — review home/away and the opponent team")
        norm = {
            "date_played": row.get("DatePlayed"),
            "home_team_source_ref": _s(row.get("HomeTeam")),
            "away_team_source_ref": _s(row.get("AwayTeam")),
            "grade_source_ref": _s(row.get("Grade")),
            "venue_source_ref": _s(row.get("Ground")),
            "round": row.get("round"),  # verbatim, never used to classify
            "matchtype": row.get("matchtype"),
            "matchtype_label": MATCHTYPE_LABELS.get(row.get("matchtype")),
            "result": result,
            "result_label": RESULT_LABELS.get(result) if result_known else None,
            "result_status": "known" if result_known else "unresolved",
            # Structured classification candidate (revised model): explicit, unverified.
            "classification": "unclassified",
            "finals_stage": None,
            "classification_verified": False,
            "classification_candidate_hint": _round_classification_hint(row.get("round") or ""),
            "classification_status": "unresolved",
            "home_points": row.get("homebpoints"),
            "away_points": row.get("awaybpoints"),
            # Match-specific captains / wicketkeepers (CricketStatz PlayerIDs; 0 = none, never
            # inferred). Preserved verbatim so promotion can link them to the correct people and so
            # provenance survives. A player set as both captain and keeper keeps both roles.
            "home_captain_source_ref": _ref0(row.get("homecaptain1")),
            "home_keeper_source_ref": _ref0(row.get("homekeeper1")),
            "home_keeper2_source_ref": _ref0(row.get("homekeeper2")),
            "away_captain_source_ref": _ref0(row.get("awaycaptain1")),
            "away_keeper_source_ref": _ref0(row.get("awaykeeper1")),
            "away_keeper2_source_ref": _ref0(row.get("awaykeeper2")),
            # Toss winner is a home/away code (0 = not recorded, 1 = home side, 2 = away side) —
            # the same convention CricketStatz uses for Result. Captured verbatim; the winning TEAM
            # is resolved at promotion. The source carries no bat/bowl decision, so the decision is
            # left unknown and never inferred from the batting order or result.
            "toss_won_by_code": row.get("tosswonby"),
        }
        # Intra-club match: point the away side at the distinct opponent so home/away are two teams.
        if opp is not None:
            norm["away_team_source_ref"] = opp["ref"]
        # Matches are staged structurally only; never promoted in Stage 6 (no canonical match table).
        _insert_record(conn, workspace_id, batch_id, "match", ref, row, norm,
                       status="staged", resolution="staged_only", issues=issues)
    counts["match"] = len(payload.get("matches") or [])

    _stage_scorecards(conn, workspace_id, batch_id, payload, counts, opponents)

    conn.execute(
        text("UPDATE import_batch SET counts = CAST(:c AS jsonb) WHERE id = :id"),
        {"c": json.dumps(counts), "id": batch_id},
    )
    audit.write_audit(conn, workspace_id, actor, "import.stage", entity="import_batch",
                      entity_id=str(batch_id), after={"counts": counts, "filename": filename})
    return {"batch_id": batch_id, "counts": counts, "status": "staged"}


def _s(v: Any) -> str | None:
    return None if v is None else str(v)


def _ref0(v: Any) -> str | None:
    """A CricketStatz person/entity reference, where 0/blank means none/unknown (never a real id)."""
    return None if v in (None, 0, "0", "") else str(v)


def _toss_winner_team(code: Any, home_id: UUID | None, away_id: UUID | None) -> UUID | None:
    """Map a CricketStatz ``tosswonby`` code to the winning team. 1 = home side, 2 = away side
    (the same home/away convention as Result); 0/blank/unknown → not recorded, so unknown."""
    if code in (1, "1"):
        return home_id
    if code in (2, "2"):
        return away_id
    return None


def _intra_club_opponents(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Find matches whose source lists the SAME team on both sides and describe a distinct opponent
    side for each.

    CricketStatz sometimes records both sides of a match under one team id — an intra-club game the
    source could not tell apart (e.g. two sides of a club before they merged), or a one-sided card.
    A team can never bat against itself in the model, so rather than drop such a match (losing a real
    scorecard) we give its away side its own distinct, clearly-flagged identity that carries the same
    club as the original side. It is deterministic (idempotent on re-import), per-match (so each gets
    its own review), and never auto-merged — an administrator renames or merges it to the correct side.
    Returns ``{match_source_ref: {ref, name, club_ref, orig_ref}}``."""
    team_meta: dict[str, tuple[str | None, str | None]] = {}
    for t in payload.get("teams") or []:
        ref = _s(t.get("TeamID"))
        if ref is not None:
            team_meta[ref] = (t.get("Name"), _s(t.get("ClubID")))
    opponents: dict[str, dict[str, Any]] = {}
    for m in payload.get("matches") or []:
        mref = _s(m.get("MatchID"))
        home = _s(m.get("HomeTeam"))
        away = _s(m.get("AwayTeam"))
        if mref is None or home is None or home != away:
            continue  # a genuine two-team fixture, or no teams at all — nothing to split
        orig_name, club_ref = team_meta.get(home, (None, None))
        date = _s(m.get("DatePlayed")) or ""
        day = date[:10] if date else mref
        opponents[mref] = {
            "ref": f"{home}~opp~{mref}",
            "name": f"{orig_name or f'team {home}'} (opponent {day})",
            "club_ref": club_ref,
            "orig_ref": home,
        }
    return opponents


def _stage_scorecards(
    conn: Connection, wid: UUID, batch_id: UUID, payload: dict[str, Any], counts: dict[str, int],
    opponents: dict[str, dict[str, Any]] | None = None,
) -> None:
    """Stage the nested CricketStatz scorecard body (``innings`` / ``batting`` / ``bowling``) verbatim.

    Dismissals: the raw ``Howout`` code is ALWAYS preserved (``howout_code``) and the mapped
    ``dismissal_type`` is left NULL — **unresolved** — because no CricketStatz code legend is
    confirmed; every code is flagged for later administrator mapping (no re-import needed). Valid
    batting/bowling/extras/fall-of-wicket data is still staged even when the dismissal is unresolved.
    Empty padding rows (``BatsmanID``/``bowlerID`` = 0) are skipped — they are not real entries.
    Fall of wickets come from the parallel FOW fields on the batting rows (row N = the Nth wicket:
    ``FOW`` score, ``FOWBatID`` the batter out) — factual source values, never inferred."""
    n_inn = n_bat = n_bowl = n_fow = 0
    opponents = opponents or {}

    for wrap in payload.get("innings") or []:
        mref = _s(wrap.get("MatchID"))
        opp = opponents.get(mref)
        for inn in wrap.get("cricket_Innings") or []:
            iid = inn.get("InningsID")
            if iid is None:
                continue
            bat_ref = _ref0(inn.get("battingteam"))
            bowl_ref = _ref0(inn.get("bowlingteam"))
            # Intra-club match (same team both sides in the source): split by innings parity so each
            # innings has two distinct sides — odd innings the original side bats, even the opponent.
            # This keeps every player on one side throughout the match (their batting and bowling
            # innings stay together); the home/away label is flagged for review.
            if opp is not None:
                try:
                    even = int(inn.get("InnsNumber") or 1) % 2 == 0
                except (TypeError, ValueError):
                    even = False
                if even:
                    bat_ref = opp["ref"]
                else:
                    bowl_ref = opp["ref"]
            _insert_record(conn, wid, batch_id, "innings", _s(iid), inn, {
                "match_source_ref": mref, "inns_number": inn.get("InnsNumber"),
                "batting_team_source_ref": bat_ref,
                "bowling_team_source_ref": bowl_ref,
                "byes": inn.get("Byes"), "legbyes": inn.get("Legbyes"),
                "wides": inn.get("Wides"), "noballs": inn.get("Noballs"),
                "iresult_raw": _s(inn.get("iresult")),
            }, resolution="new")
            n_inn += 1

    for wrap in payload.get("batting") or []:
        for inn in wrap.get("cricket_Innings") or []:
            iref = _s(inn.get("InningsID"))
            for b in inn.get("cricket_batting") or []:
                if not b:
                    continue
                batter = _ref0(b.get("BatsmanID"))
                if batter is not None:  # skip empty padding slots (BatsmanID 0)
                    howout = b.get("Howout")
                    mapped = map_howout(howout)
                    _insert_record(
                        conn, wid, batch_id, "batting_entry", f"{iref}:{b.get('Batpos')}", b, {
                            "innings_source_ref": iref, "batter_source_ref": batter,
                            "batting_position": b.get("Batpos"), "runs": b.get("Score"),
                            "balls_faced": b.get("Balls") or None, "fours": b.get("fours"),
                            "sixes": b.get("sixes"), "minutes": b.get("mins") or None,
                            "bowler_source_ref": _ref0(b.get("Bowler")),
                            "fielder_source_ref": _ref0(b.get("Fielder")),
                            "howout_code": howout, "dismissal_type": mapped,
                        },
                        # only genuinely-unmapped codes are flagged for review; the raw code is kept
                        issues=None if mapped is not None else [
                            f"howout_unresolved: code {howout} not in the verified legend (preserved for review)"],
                    )
                    n_bat += 1
                # fall of wicket (parallel array on the batting rows): the Nth wicket
                if _ref0(b.get("FOWBatID")) is not None and b.get("FOW"):
                    _insert_record(conn, wid, batch_id, "fall_of_wicket", f"{iref}:{b.get('FOWPos')}", b, {
                        "innings_source_ref": iref, "wicket_number": b.get("FOWPos"),
                        "team_score": b.get("FOW"), "dismissed_source_ref": _ref0(b.get("FOWBatID")),
                        "overs_text": _s(b.get("FOWOvers")),
                    }, resolution="new")
                    n_fow += 1

    for wrap in payload.get("bowling") or []:
        for inn in wrap.get("cricket_Innings") or []:
            iref = _s(inn.get("InningsID"))
            for order, bw in enumerate(inn.get("cricket_bowling") or [], start=1):
                bowler = _ref0(bw.get("bowlerID")) if bw else None
                if bowler is None:  # skip empty padding slots (bowlerID 0)
                    continue
                # skip squad members who did not actually bowl (all figures zero/blank) — these are
                # CricketStatz padding, not a bowling performance. A single nonzero figure keeps it.
                if not any((bw.get("Overs"), bw.get("Maidens"), bw.get("Wickets"),
                            bw.get("RunsA"), bw.get("wides"), bw.get("noballs"))):
                    continue
                _insert_record(conn, wid, batch_id, "bowling_entry", f"{iref}:{bowler}:{order}", bw, {
                    "innings_source_ref": iref, "bowler_source_ref": bowler, "bowling_order": order,
                    "overs_text": _s(bw.get("Overs")), "maidens": bw.get("Maidens"),
                    "wickets": bw.get("Wickets"), "runs_conceded": bw.get("RunsA"),
                    "wides": bw.get("wides"), "noballs": bw.get("noballs"),
                }, resolution="new")
                n_bowl += 1

    counts.update({"innings": n_inn, "batting_entry": n_bat, "bowling_entry": n_bowl, "fall_of_wicket": n_fow})


def unresolved_howout_report(payload: dict[str, Any]) -> dict[str, Any]:
    """Report every distinct ``Howout`` code in the source batting data with its frequency and a few
    representative examples (MatchID / InningsID / batting row) — so the codes' meanings can be
    investigated before any are mapped. Reads the payload only; changes nothing."""
    freq: dict[str, int] = {}
    examples: dict[str, list[dict[str, Any]]] = {}
    for wrap in payload.get("batting") or []:
        mid = wrap.get("MatchID")
        for inn in wrap.get("cricket_Innings") or []:
            iid = inn.get("InningsID")
            for b in inn.get("cricket_batting") or []:
                if not b or not _ref0(b.get("BatsmanID")):
                    continue
                code = str(b.get("Howout"))
                freq[code] = freq.get(code, 0) + 1
                ex = examples.setdefault(code, [])
                if len(ex) < 3:
                    ex.append({"match_id": mid, "innings_id": iid, "batsman_id": b.get("BatsmanID"),
                               "bowler": b.get("Bowler"), "fielder": b.get("Fielder"),
                               "score": b.get("Score")})
    codes = sorted(freq, key=lambda c: (-freq[c], c))
    return {"unresolved_codes": [{"code": c, "count": freq[c], "examples": examples[c]} for c in codes],
            "total_batting_rows": sum(freq.values())}


# --------------------------------------------------------------------------- validate


def validate_batch(conn: Connection, workspace_id: UUID, actor: str, batch_id: UUID) -> dict[str, Any]:
    """Referential-integrity checks across staged rows; records (never drops) any broken refs."""
    if get_batch(conn, batch_id) is None:
        raise ValueError("batch_not_found")
    club_refs = {r["source_ref"] for r in _staged(conn, batch_id, "club")}
    team_refs = {r["source_ref"] for r in _staged(conn, batch_id, "team")}
    venue_refs = {r["source_ref"] for r in _staged(conn, batch_id, "venue")}
    div_refs = {r["source_ref"] for r in _staged(conn, batch_id, "division")}

    problems = 0
    for rec in _staged(conn, batch_id, "team"):
        norm = rec["normalised"] or {}
        if norm.get("club_source_ref") and norm["club_source_ref"] not in club_refs:
            problems += _flag(conn, rec["id"], "club_ref_unresolved")
    for rec in list_records(conn, batch_id, entity_type="match"):
        norm = rec["normalised"] or {}
        for key, refs, label in (
            ("home_team_source_ref", team_refs, "home_team_ref_unresolved"),
            ("away_team_source_ref", team_refs, "away_team_ref_unresolved"),
            ("grade_source_ref", div_refs, "grade_ref_unresolved"),
            ("venue_source_ref", venue_refs, "venue_ref_unresolved"),
        ):
            if norm.get(key) and norm[key] not in refs:
                problems += _flag(conn, rec["id"], label)

    conn.execute(text("UPDATE import_batch SET status = 'validated' WHERE id = :id"), {"id": batch_id})
    audit.write_audit(conn, workspace_id, actor, "import.validate", entity="import_batch",
                      entity_id=str(batch_id), after={"ref_problems": problems})
    return {"batch_id": batch_id, "status": "validated", "ref_problems": problems}


def _flag(conn: Connection, record_id: UUID, issue: str) -> int:
    # Append the issue as a one-element JSON array (avoids a `::text` cast adjacent to a bind
    # param, which SQLAlchemy's text() mis-parses).
    conn.execute(
        text(
            "UPDATE import_staging_record "
            "SET issues = coalesce(issues, '[]'::jsonb) || CAST(:iss AS jsonb) WHERE id = :id"
        ),
        {"iss": json.dumps([issue]), "id": record_id},
    )
    return 1


# --------------------------------------------------------------------------- preview


def preview_batch(conn: Connection, batch_id: UUID) -> dict[str, Any]:
    """Read-only summary of what promotion would do; promotes nothing."""
    if get_batch(conn, batch_id) is None:
        raise ValueError("batch_not_found")
    rows = conn.execute(
        text(
            "SELECT entity_type, status, count(*) n FROM import_staging_record "
            "WHERE batch_id = :b GROUP BY entity_type, status ORDER BY entity_type, status"
        ),
        {"b": batch_id},
    ).mappings().all()
    summary: dict[str, dict[str, int]] = {}
    for r in rows:
        summary.setdefault(r["entity_type"], {})[r["status"]] = r["n"]
    promotable = sum(
        v.get("staged", 0) for k, v in summary.items()
        if k in ("club", "venue", "team", "division", "match",
                 "innings", "batting_entry", "bowling_entry", "fall_of_wicket")
    )
    unresolved = sum(v.get("unresolved", 0) for v in summary.values())
    return {
        "batch_id": str(batch_id),
        "by_entity": summary,
        "promotable_now": promotable,
        "unresolved": unresolved,
        "matches_promotable": summary.get("match", {}).get("staged", 0),
    }


# --------------------------------------------------------------------------- promote


def _find_canonical_by_source(
    conn: Connection, table: str, fk_col: str, source_ref: str, source_system: str = SOURCE_SYSTEM
) -> UUID | None:
    """Existing canonical id for a source_ref via the entity's source-identity table, scoped to the
    batch's ``source_system`` (so each source resolves against its own identities)."""
    return conn.execute(
        text(
            f"SELECT {fk_col} FROM {table} WHERE source_system = :ss AND source_ref = :sr LIMIT 1"
        ),
        {"ss": source_system, "sr": source_ref},
    ).scalar_one_or_none()


def _get_or_create_import_competition(
    conn: Connection, workspace_id: UUID, actor: str, source_system: str = SOURCE_SYSTEM,
) -> UUID:
    existing = _find_canonical_by_source(
        conn, "competition_source_identity", "competition_id", _IMPORT_COMP_REF, source_system)
    if existing is not None:
        return existing
    # the per-source container that holds grades imported from this source's divisions
    label = "Cricket Statz Import" if source_system == SOURCE_SYSTEM else f"{source_system} Import"
    return competitions.create_competition(
        conn, workspace_id, actor, name=label,
        notes=f"Container for grades imported from {source_system}.",
        source_system=source_system, source_ref=_IMPORT_COMP_REF,
    )


def _set_record(conn: Connection, record_id: UUID, *, status: str, resolution: str, canonical_id: UUID | None) -> None:
    conn.execute(
        text(
            "UPDATE import_staging_record SET status = :st, resolution = :res, matched_canonical_id = :cid WHERE id = :id"
        ),
        {"st": status, "res": resolution, "cid": canonical_id, "id": record_id},
    )


def promote_batch(conn: Connection, workspace_id: UUID, actor: str, batch_id: UUID) -> dict[str, Any]:
    """Promote staged, promotable rows into canonical tables (explicit admin approval).

    Idempotent: a row whose source_ref already exists canonically is *matched*, never duplicated;
    names are never auto-merged. Unresolved divisions and all matches are left in staging.
    """
    batch = get_batch(conn, batch_id)
    if batch is None:
        raise ValueError("batch_not_found")
    if batch["status"] in ("cancelled", "promoted"):
        raise ValueError(f"batch_{batch['status']}")
    ss = batch.get("source_system") or SOURCE_SYSTEM   # resolve identities against THIS source

    _SCORE = ("innings", "batting_entry", "bowling_entry", "fall_of_wicket", "partnership")
    created = {"club": 0, "venue": 0, "team": 0, "division": 0, "match": 0, **{k: 0 for k in _SCORE}}
    matched = {"club": 0, "venue": 0, "team": 0, "division": 0, "match": 0, **{k: 0 for k in _SCORE}}

    def promotable(entity_type: str) -> list[dict[str, Any]]:
        # Only 'staged' rows promote: 'unresolved' (ambiguous grades) and already-'promoted'
        # rows are skipped, so promotion is safe to re-run and never touches ambiguous data.
        return list_records(conn, batch_id, entity_type=entity_type, status="staged")

    # clubs -> organisation
    for rec in promotable("club"):
        norm = rec["normalised"] or {}
        existing = _find_canonical_by_source(conn, "organisation_source_identity", "organisation_id", rec["source_ref"], ss)
        if existing is not None:
            _set_record(conn, rec["id"], status="promoted", resolution="matched", canonical_id=existing)
            matched["club"] += 1
            continue
        oid = organisations.create_organisation(
            conn, workspace_id, actor, name=norm.get("name") or "(unnamed club)", kind="club",
            source_system=ss, source_ref=rec["source_ref"],
        )
        _set_record(conn, rec["id"], status="promoted", resolution="new", canonical_id=oid)
        created["club"] += 1

    # venues
    for rec in promotable("venue"):
        norm = rec["normalised"] or {}
        existing = _find_canonical_by_source(conn, "venue_source_identity", "venue_id", rec["source_ref"], ss)
        if existing is not None:
            _set_record(conn, rec["id"], status="promoted", resolution="matched", canonical_id=existing)
            matched["venue"] += 1
            continue
        vid = venues.create_venue(
            conn, workspace_id, actor, name=norm.get("name") or "Unknown venue",
            source_system=ss, source_ref=rec["source_ref"],
        )
        _set_record(conn, rec["id"], status="promoted", resolution="new", canonical_id=vid)
        created["venue"] += 1

    # divisions -> grade (confident only; ambiguous stay unresolved and are not in 'staged')
    comp_id: UUID | None = None
    confident_divs = promotable("division")
    if confident_divs:
        comp_id = _get_or_create_import_competition(conn, workspace_id, actor, ss)
    for rec in confident_divs:
        norm = rec["normalised"] or {}
        existing = conn.execute(
            text("SELECT id FROM grade WHERE competition_id = :c AND source_ref = :sr"),
            {"c": comp_id, "sr": rec["source_ref"]},
        ).scalar_one_or_none()
        if existing is not None:
            _set_record(conn, rec["id"], status="promoted", resolution="matched", canonical_id=existing)
            matched["division"] += 1
            continue
        gid = competitions.create_grade(
            conn, workspace_id, actor, comp_id, name=norm.get("name") or "(grade)",
            source_system=ss, source_ref=rec["source_ref"],
        )
        _set_record(conn, rec["id"], status="promoted", resolution="new", canonical_id=gid)
        created["division"] += 1

    # teams -> team (needs its club promoted/matched first)
    for rec in promotable("team"):
        norm = rec["normalised"] or {}
        existing = _find_canonical_by_source(conn, "team_source_identity", "team_id", rec["source_ref"], ss)
        if existing is not None:
            _set_record(conn, rec["id"], status="promoted", resolution="matched", canonical_id=existing)
            matched["team"] += 1
            continue
        club_ref = norm.get("club_source_ref")
        org_id = _find_canonical_by_source(conn, "organisation_source_identity", "organisation_id", club_ref, ss) if club_ref else None
        if org_id is None:
            _flag(conn, rec["id"], "club_not_promoted: team left staged")
            continue
        tid = teams.create_team(
            conn, workspace_id, actor, organisation_id=org_id, name=norm.get("name") or "(team)",
            source_system=ss, source_ref=rec["source_ref"],
        )
        _set_record(conn, rec["id"], status="promoted", resolution="new", canonical_id=tid)
        created["team"] += 1

    # matches -> match (canonical fixture header). Stage 8: matches are now promoted (the scorecard
    # body — innings/batting/bowling/FOW/partnerships — is promoted by a later sub-stage). Idempotent
    # on (source_system, source_ref): re-promotion matches, never duplicates. References (teams,
    # grade, venue) are linked only where those entities were themselves promoted/matched — an
    # unresolved reference stays NULL (unknown ≠ wrong) and is flagged, never invented. The round
    # label NEVER classifies the match: classification stays 'unclassified'/unverified for admin.
    promotable_matches = promotable("match")
    if promotable_matches and comp_id is None:
        comp_id = _get_or_create_import_competition(conn, workspace_id, actor, ss)
    for rec in promotable_matches:
        norm = rec["normalised"] or {}
        existing = conn.execute(
            text("SELECT id FROM match WHERE source_system = :ss AND source_ref = :sr"),
            {"ss": ss, "sr": rec["source_ref"]},
        ).scalar_one_or_none()
        if existing is not None:
            _set_record(conn, rec["id"], status="promoted", resolution="matched", canonical_id=existing)
            matched["match"] += 1
            # R1: record THIS source against the already-existing match as additional evidence —
            # never overwriting the approved scorecard; conflicts are surfaced for admin review.
            match_sources.attach_source(conn, workspace_id, actor, existing, source_system=ss,
                                        source_ref=rec["source_ref"], recorded_fields=norm,
                                        filename=batch.get("source_filename"), sha256=batch.get("source_sha256"))
            continue

        def _resolve(table: str, fk: str, key: str, _norm: dict[str, Any] = norm, _ss: str = ss) -> UUID | None:
            ref = _norm.get(key)
            return _find_canonical_by_source(conn, table, fk, ref, _ss) if ref else None

        home_id = _resolve("team_source_identity", "team_id", "home_team_source_ref")
        away_id = _resolve("team_source_identity", "team_id", "away_team_source_ref")
        grade_id = _resolve("grade", "id", "grade_source_ref")
        venue_id = _resolve("venue_source_identity", "venue_id", "venue_source_ref")
        match_date = norm.get("date_played")

        mid = matches.create_match(
            conn, workspace_id, actor, competition_id=comp_id, grade_id=grade_id, venue_id=venue_id,
            match_date=match_date, date_precision="exact" if match_date else "unknown",
            round=norm.get("round"), matchtype=norm.get("matchtype_label"),
            source_system=ss, source_ref=rec["source_ref"],
        )
        # Resolve match-specific captains/keepers to people (0/absent → unset; never invented).
        # A single player named as both captain and keeper keeps both roles distinctly.
        home_captain = _person_by_source(conn, norm.get("home_captain_source_ref"), ss)
        home_keeper = _person_by_source(conn, norm.get("home_keeper_source_ref"), ss)
        home_keeper2 = _person_by_source(conn, norm.get("home_keeper2_source_ref"), ss)
        away_captain = _person_by_source(conn, norm.get("away_captain_source_ref"), ss)
        away_keeper = _person_by_source(conn, norm.get("away_keeper_source_ref"), ss)
        away_keeper2 = _person_by_source(conn, norm.get("away_keeper2_source_ref"), ss)
        # link the sides that resolved; a missing team leaves that side unset and is flagged
        if home_id is not None:
            matches.set_team(conn, workspace_id, actor, mid, team_id=home_id, is_home=True,
                             captain_person_id=home_captain, wicketkeeper_person_id=home_keeper,
                             wicketkeeper2_person_id=home_keeper2)
        else:
            _flag(conn, rec["id"], "home_team_unresolved: match imported without home side")
        if away_id is not None:
            matches.set_team(conn, workspace_id, actor, mid, team_id=away_id, is_home=False,
                             captain_person_id=away_captain, wicketkeeper_person_id=away_keeper,
                             wicketkeeper2_person_id=away_keeper2)
        else:
            _flag(conn, rec["id"], "away_team_unresolved: match imported without away side")
        # Toss winner (home/away code 1/2 → that side; 0/absent → not recorded, left unknown). The
        # decision to bat/bowl is not in the source, so it stays unknown — never inferred.
        toss_team = _toss_winner_team(norm.get("toss_won_by_code"), home_id, away_id)
        if toss_team is not None:
            matches.set_toss(conn, workspace_id, actor, mid, toss_winner_team_id=toss_team)
        # preserve the raw CricketStatz result code; set a known winner only where evidence-verified
        rtype = norm.get("result_label") if norm.get("result_status") == "known" else "unknown"
        won_by = home_id if rtype == "home_win" else away_id if rtype == "away_win" else None
        result = norm.get("result")
        # a known CricketStatz result is preserved as 'recorded'; an unknown one is left 'unknown'
        # so Stage 7.3 can calculate it from the imported scorecard where the evidence supports it.
        matches.set_result(conn, workspace_id, actor, mid, result_type=rtype or "unknown",
                           won_by_team_id=won_by, result_raw=None if result is None else str(result),
                           result_source="recorded" if norm.get("result_status") == "known" else "unknown")
        # classification is intentionally NOT set here — the round is a hint only (user rule).
        # R1: record this source as the match's first source (its own provenance for conflict review).
        match_sources.attach_source(conn, workspace_id, actor, mid, source_system=ss,
                                    source_ref=rec["source_ref"], recorded_fields=norm,
                                    filename=batch.get("source_filename"), sha256=batch.get("source_sha256"))
        _set_record(conn, rec["id"], status="promoted", resolution="new", canonical_id=mid)
        created["match"] += 1

    _promote_scorecards(conn, workspace_id, actor, batch_id, created, matched, ss)

    remaining_unresolved = conn.execute(
        text("SELECT count(*) FROM import_staging_record WHERE batch_id = :b AND status IN ('staged','unresolved')"),
        {"b": batch_id},
    ).scalar_one()
    new_status = "promoted" if remaining_unresolved == 0 else "partially_promoted"
    conn.execute(
        text("UPDATE import_batch SET status = :st, promoted_at = now(), promoted_by = :by WHERE id = :id"),
        {"st": new_status, "by": actor, "id": batch_id},
    )
    audit.write_audit(conn, workspace_id, actor, "import.promote", entity="import_batch",
                      entity_id=str(batch_id), after={"created": created, "matched": matched, "status": new_status})
    return {"batch_id": str(batch_id), "status": new_status, "created": created, "matched": matched}


# --------------------------------------------------------------------------- cancel / rollback


def cancel_batch(conn: Connection, workspace_id: UUID, actor: str, batch_id: UUID) -> dict[str, Any]:
    """Cancel a batch that has not promoted anything into canonical tables."""
    batch = get_batch(conn, batch_id)
    if batch is None:
        raise ValueError("batch_not_found")
    promoted = conn.execute(
        text("SELECT count(*) FROM import_staging_record WHERE batch_id = :b AND resolution = 'new' AND status = 'promoted'"),
        {"b": batch_id},
    ).scalar_one()
    if promoted:
        raise ValueError("batch_has_promoted_rows_use_rollback")
    conn.execute(text("UPDATE import_batch SET status = 'cancelled' WHERE id = :id"), {"id": batch_id})
    audit.write_audit(conn, workspace_id, actor, "import.cancel", entity="import_batch", entity_id=str(batch_id))
    return {"batch_id": str(batch_id), "status": "cancelled"}


def _person_by_source(conn: Connection, ref: str | None, source_system: str = SOURCE_SYSTEM) -> UUID | None:
    """OneStats person_id for a source PlayerID (via the people import's source identity), scoped to
    the batch's source system."""
    if ref is None:
        return None
    return conn.execute(
        text("SELECT person_id FROM person_source_identity WHERE source_system = :ss AND source_ref = :sr LIMIT 1"),
        {"ss": source_system, "sr": ref},
    ).scalar_one_or_none()


def backfill_imported_match_details(conn: Connection, workspace_id: UUID, actor: str) -> dict[str, int]:
    """Fill captains/wicketkeepers and the toss winner on already-imported CricketStatz matches from
    their staged source rows, WITHOUT re-importing and WITHOUT creating or duplicating any people or
    matches.

    Non-destructive and safe to re-run: a value is set only where the match currently has it unset,
    so any manual correction already made by a user is preserved. Source refs of 0/absent are left
    unset — nothing is inferred (the toss winner is never guessed from batting order or result, and
    the bat/bowl decision, absent from the source, is left unknown). A player named as both captain
    and keeper keeps both roles. Returns how many sides/roles were filled and tosses were set.
    """
    rows = conn.execute(
        text("SELECT r.raw, r.matched_canonical_id AS canonical_id FROM import_staging_record r "
             "JOIN match m ON m.id = r.matched_canonical_id "
             "WHERE r.entity_type = 'match' AND r.matched_canonical_id IS NOT NULL "
             "AND m.source_system = :ss"),
        {"ss": SOURCE_SYSTEM},
    ).mappings().all()
    sides_updated = 0
    roles_filled = 0
    toss_set = 0
    for row in rows:
        raw = row["raw"] or {}
        mid = row["canonical_id"]
        for is_home, cap_key, wk_key, wk2_key in (
            (True, "homecaptain1", "homekeeper1", "homekeeper2"),
            (False, "awaycaptain1", "awaykeeper1", "awaykeeper2"),
        ):
            cap = _person_by_source(conn, _ref0(raw.get(cap_key)))
            wk = _person_by_source(conn, _ref0(raw.get(wk_key)))
            wk2 = _person_by_source(conn, _ref0(raw.get(wk2_key)))
            if cap is None and wk is None and wk2 is None:
                continue
            # Only touch a side where a currently-unset role has a resolved person to fill it, so
            # the operation is genuinely idempotent and never rewrites a value that is already set.
            res = conn.execute(
                text("UPDATE match_team SET "
                     "captain_person_id = COALESCE(captain_person_id, CAST(:cap AS uuid)), "
                     "wicketkeeper_person_id = COALESCE(wicketkeeper_person_id, CAST(:wk AS uuid)), "
                     "wicketkeeper2_person_id = COALESCE(wicketkeeper2_person_id, CAST(:wk2 AS uuid)) "
                     "WHERE match_id = :m AND is_home = :h AND ("
                     "   (captain_person_id IS NULL AND CAST(:cap AS uuid) IS NOT NULL) "
                     "OR (wicketkeeper_person_id IS NULL AND CAST(:wk AS uuid) IS NOT NULL) "
                     "OR (wicketkeeper2_person_id IS NULL AND CAST(:wk2 AS uuid) IS NOT NULL))"),
                {"cap": cap, "wk": wk, "wk2": wk2, "m": mid, "h": is_home},
            )
            if res.rowcount:
                sides_updated += res.rowcount
                roles_filled += sum(1 for v in (cap, wk, wk2) if v is not None)
        # Toss winner (home/away code), only where the match has no toss winner recorded yet.
        sides = conn.execute(
            text("SELECT team_id, is_home FROM match_team WHERE match_id = :m"), {"m": mid},
        ).mappings().all()
        home_id = next((s["team_id"] for s in sides if s["is_home"]), None)
        away_id = next((s["team_id"] for s in sides if not s["is_home"]), None)
        toss_team = _toss_winner_team(raw.get("tosswonby"), home_id, away_id)
        if toss_team is not None:
            res = conn.execute(
                text("UPDATE match SET toss_winner_team_id = :t, updated_at = now() "
                     "WHERE id = :m AND toss_winner_team_id IS NULL"),
                {"t": toss_team, "m": mid},
            )
            toss_set += res.rowcount
    audit.write_audit(conn, workspace_id, actor, "import.backfill_match_details", entity="workspace",
                      entity_id=str(workspace_id),
                      after={"sides_updated": sides_updated, "roles_filled": roles_filled, "toss_set": toss_set})
    return {"sides_updated": sides_updated, "roles_filled": roles_filled, "toss_set": toss_set}


def _canonical_by_source(conn: Connection, table: str, ref: str, source_system: str = SOURCE_SYSTEM) -> UUID | None:
    return conn.execute(
        text(f"SELECT id FROM {table} WHERE source_system = :ss AND source_ref = :sr LIMIT 1"),
        {"ss": source_system, "sr": ref},
    ).scalar_one_or_none()


def _promote_scorecards(
    conn: Connection, wid: UUID, actor: str, batch_id: UUID,
    created: dict[str, int], matched: dict[str, int], source_system: str = SOURCE_SYSTEM,
) -> None:
    """Promote the staged scorecard body into the existing innings/batting/bowling/FOW models.

    Idempotent on (source_system, source_ref) for every row — re-promotion matches, never
    duplicates. Player references resolve via the people import's source identities; an unresolved
    reference stays NULL and is flagged (unknown ≠ wrong), never invented. Dismissal TYPE is left
    unresolved (NULL) with the raw ``Howout`` preserved in ``dismissal_source_code``; all other
    figures (runs, balls, boundaries, extras, bowling, fall of wickets) import regardless, so a
    historically incomplete or unresolved-dismissal card is still imported, never rejected."""
    def staged(et: str) -> list[dict[str, Any]]:
        return list_records(conn, batch_id, entity_type=et, status="staged")

    touched_innings: set[UUID] = set()  # innings to (re)derive partnerships for after FOW import

    # innings -> innings (needs its match promoted/matched; sides linked where teams resolved)
    for rec in staged("innings"):
        norm = rec["normalised"] or {}
        existing = _canonical_by_source(conn, "innings", rec["source_ref"], source_system)
        if existing is not None:
            _set_record(conn, rec["id"], status="promoted", resolution="matched", canonical_id=existing)
            matched["innings"] += 1
            touched_innings.add(existing)
            continue
        match_id = _canonical_by_source(conn, "match", norm.get("match_source_ref"), source_system) if norm.get("match_source_ref") else None
        if match_id is None:
            _flag(conn, rec["id"], "match_unresolved: innings left staged")
            continue
        bat_team = _find_canonical_by_source(conn, "team_source_identity", "team_id", norm["batting_team_source_ref"], source_system) if norm.get("batting_team_source_ref") else None
        bowl_team = _find_canonical_by_source(conn, "team_source_identity", "team_id", norm["bowling_team_source_ref"], source_system) if norm.get("bowling_team_source_ref") else None
        iid = innings.create_innings(
            conn, wid, actor, match_id=match_id, inns_number=norm.get("inns_number") or 1,
            batting_team_id=bat_team, bowling_team_id=bowl_team,
            byes=norm.get("byes"), legbyes=norm.get("legbyes"), wides=norm.get("wides"),
            noballs=norm.get("noballs"), iresult_raw=norm.get("iresult_raw"),
            source_system=source_system, source_ref=rec["source_ref"],
        )
        _set_record(conn, rec["id"], status="promoted", resolution="new", canonical_id=iid)
        created["innings"] += 1
        touched_innings.add(iid)

    # batting entries -> batting_entry (dismissal TYPE unresolved; raw Howout preserved)
    for rec in staged("batting_entry"):
        norm = rec["normalised"] or {}
        existing = _canonical_by_source(conn, "batting_entry", rec["source_ref"], source_system)
        if existing is not None:
            _set_record(conn, rec["id"], status="promoted", resolution="matched", canonical_id=existing)
            matched["batting_entry"] += 1
            continue
        inns_id = _canonical_by_source(conn, "innings", norm.get("innings_source_ref"), source_system) if norm.get("innings_source_ref") else None
        if inns_id is None:
            _flag(conn, rec["id"], "innings_unresolved: batting entry left staged")
            continue
        eid = batting.create_entry(
            conn, wid, actor, innings_id=inns_id,
            person_id=_person_by_source(conn, norm.get("batter_source_ref"), source_system),
            batting_position=norm.get("batting_position"), runs=norm.get("runs"),
            balls_faced=norm.get("balls_faced"), fours=norm.get("fours"), sixes=norm.get("sixes"),
            minutes=norm.get("minutes"),
            # an adapter may pre-map the type (generic sources); else the verified CricketStatz legend
            # maps the raw code, and an unmapped code stays NULL (unresolved) with the raw code kept.
            dismissal_type=norm.get("dismissal_type") if norm.get("dismissal_type") is not None
                            else map_howout(norm.get("howout_code")),
            dismissal_source_code=_s(norm.get("dismissal_source_code") if norm.get("dismissal_source_code") is not None
                                     else norm.get("howout_code")),
            bowler_person_id=_person_by_source(conn, norm.get("bowler_source_ref"), source_system),
            fielder_person_id=_person_by_source(conn, norm.get("fielder_source_ref"), source_system),
            source_system=source_system, source_ref=rec["source_ref"],
        )
        _set_record(conn, rec["id"], status="promoted", resolution="new", canonical_id=eid)
        created["batting_entry"] += 1

    # bowling entries -> bowling_entry
    for rec in staged("bowling_entry"):
        norm = rec["normalised"] or {}
        existing = _canonical_by_source(conn, "bowling_entry", rec["source_ref"], source_system)
        if existing is not None:
            _set_record(conn, rec["id"], status="promoted", resolution="matched", canonical_id=existing)
            matched["bowling_entry"] += 1
            continue
        inns_id = _canonical_by_source(conn, "innings", norm.get("innings_source_ref"), source_system) if norm.get("innings_source_ref") else None
        if inns_id is None:
            _flag(conn, rec["id"], "innings_unresolved: bowling entry left staged")
            continue
        eid = bowling.create_entry(
            conn, wid, actor, innings_id=inns_id,
            person_id=_person_by_source(conn, norm.get("bowler_source_ref"), source_system),
            bowling_order=norm.get("bowling_order"), overs_text=norm.get("overs_text"),
            maidens=norm.get("maidens"), runs_conceded=norm.get("runs_conceded"),
            wickets=norm.get("wickets"), wides=norm.get("wides"), noballs=norm.get("noballs"),
            source_system=source_system, source_ref=rec["source_ref"],
        )
        _set_record(conn, rec["id"], status="promoted", resolution="new", canonical_id=eid)
        created["bowling_entry"] += 1

    # fall of wickets -> fall_of_wicket (factual; dismissed batter resolved where known)
    for rec in staged("fall_of_wicket"):
        norm = rec["normalised"] or {}
        existing = _canonical_by_source(conn, "fall_of_wicket", rec["source_ref"], source_system)
        if existing is not None:
            _set_record(conn, rec["id"], status="promoted", resolution="matched", canonical_id=existing)
            matched["fall_of_wicket"] += 1
            continue
        inns_id = _canonical_by_source(conn, "innings", norm.get("innings_source_ref"), source_system) if norm.get("innings_source_ref") else None
        if inns_id is None:
            _flag(conn, rec["id"], "innings_unresolved: fall of wicket left staged")
            continue
        fid = partnerships.create_fow(
            conn, wid, actor, innings_id=inns_id, wicket_number=norm.get("wicket_number"),
            team_score=norm.get("team_score"),
            dismissed_person_id=_person_by_source(conn, norm.get("dismissed_source_ref"), source_system),
            overs_text=norm.get("overs_text"),
            source_system=source_system, source_ref=rec["source_ref"],
        )
        _set_record(conn, rec["id"], status="promoted", resolution="new", canonical_id=fid)
        created["fall_of_wicket"] += 1

    # Automatic partnerships: once the batting order and fall of wickets are imported, derive the
    # CALCULATED partnerships for each touched innings (naming both batters where the order/FOW
    # supports it). Reuses the existing engine — idempotent (replaces only origin='calculated', so
    # re-import never duplicates), preserves any manual/verified partnerships, and invents nothing
    # when an innings has no FOW (the stand is simply left unknown).
    derived_total = 0
    for inns_id in touched_innings:
        try:
            parts = partnerships.derive_from_fow(conn, wid, actor, inns_id)
            derived_total += sum(1 for p in parts if p.get("origin") == "calculated")
        except ValueError:
            pass  # an innings that cannot be derived is left without partnerships, never blocked
    created["partnership"] = created.get("partnership", 0) + derived_total

    # Phase 7.3: calculate match results from the imported scorecard where the CricketStatz result
    # was unknown (recorded results are preserved). Non-blocking and idempotent.
    from onestats.domain import results, seasons  # local import avoids a module cycle
    match_ids = {conn.execute(text("SELECT match_id FROM innings WHERE id = :i"), {"i": i}).scalar_one()
                 for i in touched_innings}
    for mid in match_ids:
        try:
            results.auto_apply_result(conn, wid, actor, mid)
        except ValueError:
            pass
        try:
            seasons.auto_assign_season(conn, wid, actor, mid)  # Phase 7.4 (unresolved if the model is unknown)
        except ValueError:
            pass


def controlled_import(
    conn: Connection, workspace_id: UUID, actor: str, *,
    data: dict[str, Any], people: dict[str, Any] | None = None,
    commit: bool = False, filename: str | None = None,
) -> dict[str, Any]:
    """Run a controlled CricketStatz import (people, then structural + scorecards) in one pass and
    return a combined summary for the Import Wizard.

    The caller owns the transaction: for a PREVIEW (``commit=False``) nothing must persist, so the
    endpoint runs this inside a savepoint it rolls back; for a COMMIT it releases/commits. People are
    detected (and, on commit, promoted so scorecard player references resolve); structural + scorecard
    rows are staged, validated and previewed (and, on commit, promoted). Idempotent and reusing the
    existing engine — no duplicate records, workspace isolation and permissions unchanged."""
    from onestats.domain import people_import  # local import avoids a module cycle

    out: dict[str, Any] = {"people": {}, "staged": {}, "preview": {}, "howout_unresolved": [], "committed": commit}
    people_batch = None
    if people and (people.get("players") or people.get("officials")):
        people_batch = people_import.stage_people(conn, workspace_id, actor, payload=people, filename=filename)["batch_id"]
        out["people"]["detected"] = people_import.detect(conn, workspace_id, actor, people_batch)
        if commit:
            out["people"]["promoted"] = people_import.promote(conn, workspace_id, actor, people_batch)

    staged = parse_and_stage(conn, workspace_id, actor, payload=data, filename=filename)
    out["staged"] = staged["counts"]
    out["batch_id"] = str(staged["batch_id"])
    validate_batch(conn, workspace_id, actor, staged["batch_id"])
    out["preview"] = preview_batch(conn, staged["batch_id"])
    out["howout_unresolved"] = unresolved_howout_report(data)["unresolved_codes"]
    if commit:
        out["promoted"] = promote_batch(conn, workspace_id, actor, staged["batch_id"])
        # once both people and clubs exist, record each player's MyClub affiliation (for scoping)
        out["affiliations"] = link_cricketstatz_people_to_clubs(conn, workspace_id, actor, people_batch)
    return out


def link_cricketstatz_people_to_clubs(
    conn: Connection, workspace_id: UUID, actor: str, people_batch_id: UUID | None = None,
) -> dict[str, Any]:
    """Create the club affiliation each imported CricketStatz person implies — their ``MyClub`` —
    where it is not already recorded. This captures the source's player-to-club association so that
    player selectors can be scoped to a club. Idempotent (skips a person already affiliated to that
    club), never overwrites, and preserves provenance. Resolves the club only where the organisation
    was imported; an unresolved MyClub is simply skipped (never invented)."""
    from onestats.domain import affiliations  # local import avoids a module cycle

    sql = ("SELECT r.normalised, r.matched_canonical_id AS person_id, r.source_ref "
           "FROM import_staging_record r JOIN import_batch b ON b.id = r.batch_id "
           "WHERE b.source_system = :ss AND r.entity_type IN ('player','official') "
           "AND r.matched_canonical_id IS NOT NULL")
    params: dict[str, Any] = {"ss": SOURCE_SYSTEM}
    if people_batch_id is not None:
        sql += " AND r.batch_id = :b"
        params["b"] = people_batch_id
    linked = 0
    seen: set[tuple[str, str]] = set()
    for r in conn.execute(text(sql), params).mappings().all():
        norm = r["normalised"] or {}
        club_ref, pid = norm.get("myclub_source_ref"), r["person_id"]
        if not club_ref or pid is None:
            continue
        org = _find_canonical_by_source(conn, "organisation_source_identity", "organisation_id", club_ref)
        if org is None:
            continue
        key = (str(pid), str(org))
        if key in seen or conn.execute(
            text("SELECT 1 FROM person_affiliation WHERE person_id = :p AND organisation_id = :o LIMIT 1"),
            {"p": pid, "o": org},
        ).first() is not None:
            continue
        seen.add(key)
        affiliations.create_affiliation(conn, workspace_id, actor, person_id=pid, organisation_id=org,
                                        role="player", source_system=SOURCE_SYSTEM,
                                        source_ref=f"{r['source_ref']}:myclub")
        linked += 1
    return {"linked": linked}


def remap_howout_dismissals(conn: Connection, workspace_id: UUID, actor: str) -> dict[str, Any]:
    """Apply the verified CricketStatz Howout legend to ALREADY-IMPORTED batting rows, in place.

    Reads the preserved ``dismissal_source_code`` and sets ``dismissal_type`` where the code is in
    the verified legend and the type is still unresolved (NULL). Never overwrites a type already set
    (human/verified data is preserved), never creates rows (UPDATE only — no duplicates), and leaves
    codes outside the legend unresolved. Every change is audited via ``batting.update_entry``."""
    rows = conn.execute(
        text("SELECT id, dismissal_source_code FROM batting_entry "
             "WHERE source_system = :ss AND dismissal_type IS NULL AND dismissal_source_code IS NOT NULL"),
        {"ss": SOURCE_SYSTEM},
    ).mappings().all()
    updated = 0
    by_type: dict[str, int] = {}
    still_unresolved: dict[str, int] = {}
    for r in rows:
        mapped = map_howout(r["dismissal_source_code"])
        if mapped is None:
            still_unresolved[r["dismissal_source_code"]] = still_unresolved.get(r["dismissal_source_code"], 0) + 1
            continue
        batting.update_entry(conn, workspace_id, actor, r["id"], dismissal_type=mapped)
        updated += 1
        by_type[mapped] = by_type.get(mapped, 0) + 1
    audit.write_audit(conn, workspace_id, actor, "import.remap_howout", entity="workspace",
                      entity_id=str(workspace_id), after={"updated": updated, "by_type": by_type})
    return {"updated": updated, "by_type": by_type, "still_unresolved": still_unresolved}


def rollback_batch(conn: Connection, workspace_id: UUID, actor: str, batch_id: UUID) -> dict[str, Any]:
    """Reverse a promotion: delete exactly the canonical rows this batch created (resolution='new'),
    in dependency order, and return the staging records to 'staged'. Matched (pre-existing) rows are
    left untouched. Freshly imported rows have no other dependents, so deletion is safe and complete."""
    batch = get_batch(conn, batch_id)
    if batch is None:
        raise ValueError("batch_not_found")
    removed = {k: 0 for k in ("fall_of_wicket", "batting_entry", "bowling_entry", "innings",
                              "match", "team", "division", "venue", "club")}
    # children before parents: scorecard rows, then matches (match delete would cascade innings,
    # but explicit deletion keeps the staging records' resolution in step), then teams/venues/grades.
    order = [("fall_of_wicket", "fall_of_wicket"), ("batting_entry", "batting_entry"),
             ("bowling_entry", "bowling_entry"), ("innings", "innings"), ("match", "match"),
             ("team", "team"), ("division", "grade"), ("venue", "venue"), ("club", "organisation")]
    for entity_type, table in order:
        for rec in list_records(conn, batch_id, entity_type=entity_type, status="promoted"):
            if rec["resolution"] != "new" or rec["matched_canonical_id"] is None:
                continue
            conn.execute(text(f"DELETE FROM {table} WHERE id = :id"), {"id": rec["matched_canonical_id"]})
            _set_record(conn, rec["id"], status="staged", resolution="new", canonical_id=None)
            removed[entity_type] += 1
    conn.execute(
        text("UPDATE import_batch SET status = 'validated', promoted_at = NULL, promoted_by = NULL WHERE id = :id"),
        {"id": batch_id},
    )
    audit.write_audit(conn, workspace_id, actor, "import.rollback", entity="import_batch",
                      entity_id=str(batch_id), after={"removed": removed})
    return {"batch_id": str(batch_id), "status": "validated", "removed": removed}
