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
        }
        # Matches are staged structurally only; never promoted in Stage 6 (no canonical match table).
        _insert_record(conn, workspace_id, batch_id, "match", ref, row, norm,
                       status="staged", resolution="staged_only", issues=issues)
    counts["match"] = len(payload.get("matches") or [])

    _stage_scorecards(conn, workspace_id, batch_id, payload, counts)

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


def _stage_scorecards(
    conn: Connection, wid: UUID, batch_id: UUID, payload: dict[str, Any], counts: dict[str, int]
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

    for wrap in payload.get("innings") or []:
        mref = _s(wrap.get("MatchID"))
        for inn in wrap.get("cricket_Innings") or []:
            iid = inn.get("InningsID")
            if iid is None:
                continue
            _insert_record(conn, wid, batch_id, "innings", _s(iid), inn, {
                "match_source_ref": mref, "inns_number": inn.get("InnsNumber"),
                "batting_team_source_ref": _ref0(inn.get("battingteam")),
                "bowling_team_source_ref": _ref0(inn.get("bowlingteam")),
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


def _find_canonical_by_source(conn: Connection, table: str, fk_col: str, source_ref: str) -> UUID | None:
    """Existing canonical id for a CS source_ref via the entity's source-identity table."""
    return conn.execute(
        text(
            f"SELECT {fk_col} FROM {table} WHERE source_system = :ss AND source_ref = :sr LIMIT 1"
        ),
        {"ss": SOURCE_SYSTEM, "sr": source_ref},
    ).scalar_one_or_none()


def _get_or_create_import_competition(conn: Connection, workspace_id: UUID, actor: str) -> UUID:
    existing = _find_canonical_by_source(conn, "competition_source_identity", "competition_id", _IMPORT_COMP_REF)
    if existing is not None:
        return existing
    return competitions.create_competition(
        conn, workspace_id, actor, name="Cricket Statz Import",
        notes="Container for grades imported from Cricket Statz divisions.",
        source_system=SOURCE_SYSTEM, source_ref=_IMPORT_COMP_REF,
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

    _SCORE = ("innings", "batting_entry", "bowling_entry", "fall_of_wicket")
    created = {"club": 0, "venue": 0, "team": 0, "division": 0, "match": 0, **{k: 0 for k in _SCORE}}
    matched = {"club": 0, "venue": 0, "team": 0, "division": 0, "match": 0, **{k: 0 for k in _SCORE}}

    def promotable(entity_type: str) -> list[dict[str, Any]]:
        # Only 'staged' rows promote: 'unresolved' (ambiguous grades) and already-'promoted'
        # rows are skipped, so promotion is safe to re-run and never touches ambiguous data.
        return list_records(conn, batch_id, entity_type=entity_type, status="staged")

    # clubs -> organisation
    for rec in promotable("club"):
        norm = rec["normalised"] or {}
        existing = _find_canonical_by_source(conn, "organisation_source_identity", "organisation_id", rec["source_ref"])
        if existing is not None:
            _set_record(conn, rec["id"], status="promoted", resolution="matched", canonical_id=existing)
            matched["club"] += 1
            continue
        oid = organisations.create_organisation(
            conn, workspace_id, actor, name=norm.get("name") or "(unnamed club)", kind="club",
            source_system=SOURCE_SYSTEM, source_ref=rec["source_ref"],
        )
        _set_record(conn, rec["id"], status="promoted", resolution="new", canonical_id=oid)
        created["club"] += 1

    # venues
    for rec in promotable("venue"):
        norm = rec["normalised"] or {}
        existing = _find_canonical_by_source(conn, "venue_source_identity", "venue_id", rec["source_ref"])
        if existing is not None:
            _set_record(conn, rec["id"], status="promoted", resolution="matched", canonical_id=existing)
            matched["venue"] += 1
            continue
        vid = venues.create_venue(
            conn, workspace_id, actor, name=norm.get("name") or "Unknown venue",
            source_system=SOURCE_SYSTEM, source_ref=rec["source_ref"],
        )
        _set_record(conn, rec["id"], status="promoted", resolution="new", canonical_id=vid)
        created["venue"] += 1

    # divisions -> grade (confident only; ambiguous stay unresolved and are not in 'staged')
    comp_id: UUID | None = None
    confident_divs = promotable("division")
    if confident_divs:
        comp_id = _get_or_create_import_competition(conn, workspace_id, actor)
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
            source_system=SOURCE_SYSTEM, source_ref=rec["source_ref"],
        )
        _set_record(conn, rec["id"], status="promoted", resolution="new", canonical_id=gid)
        created["division"] += 1

    # teams -> team (needs its club promoted/matched first)
    for rec in promotable("team"):
        norm = rec["normalised"] or {}
        existing = _find_canonical_by_source(conn, "team_source_identity", "team_id", rec["source_ref"])
        if existing is not None:
            _set_record(conn, rec["id"], status="promoted", resolution="matched", canonical_id=existing)
            matched["team"] += 1
            continue
        club_ref = norm.get("club_source_ref")
        org_id = _find_canonical_by_source(conn, "organisation_source_identity", "organisation_id", club_ref) if club_ref else None
        if org_id is None:
            _flag(conn, rec["id"], "club_not_promoted: team left staged")
            continue
        tid = teams.create_team(
            conn, workspace_id, actor, organisation_id=org_id, name=norm.get("name") or "(team)",
            source_system=SOURCE_SYSTEM, source_ref=rec["source_ref"],
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
        comp_id = _get_or_create_import_competition(conn, workspace_id, actor)
    for rec in promotable_matches:
        norm = rec["normalised"] or {}
        existing = conn.execute(
            text("SELECT id FROM match WHERE source_system = :ss AND source_ref = :sr"),
            {"ss": SOURCE_SYSTEM, "sr": rec["source_ref"]},
        ).scalar_one_or_none()
        if existing is not None:
            _set_record(conn, rec["id"], status="promoted", resolution="matched", canonical_id=existing)
            matched["match"] += 1
            continue

        def _resolve(table: str, fk: str, key: str, _norm: dict[str, Any] = norm) -> UUID | None:
            ref = _norm.get(key)
            return _find_canonical_by_source(conn, table, fk, ref) if ref else None

        home_id = _resolve("team_source_identity", "team_id", "home_team_source_ref")
        away_id = _resolve("team_source_identity", "team_id", "away_team_source_ref")
        grade_id = _resolve("grade", "id", "grade_source_ref")
        venue_id = _resolve("venue_source_identity", "venue_id", "venue_source_ref")
        match_date = norm.get("date_played")

        mid = matches.create_match(
            conn, workspace_id, actor, competition_id=comp_id, grade_id=grade_id, venue_id=venue_id,
            match_date=match_date, date_precision="exact" if match_date else "unknown",
            round=norm.get("round"), matchtype=norm.get("matchtype_label"),
            source_system=SOURCE_SYSTEM, source_ref=rec["source_ref"],
        )
        # link the sides that resolved; a missing team leaves that side unset and is flagged
        if home_id is not None:
            matches.set_team(conn, workspace_id, actor, mid, team_id=home_id, is_home=True)
        else:
            _flag(conn, rec["id"], "home_team_unresolved: match imported without home side")
        if away_id is not None:
            matches.set_team(conn, workspace_id, actor, mid, team_id=away_id, is_home=False)
        else:
            _flag(conn, rec["id"], "away_team_unresolved: match imported without away side")
        # preserve the raw CricketStatz result code; set a known winner only where evidence-verified
        rtype = norm.get("result_label") if norm.get("result_status") == "known" else "unknown"
        won_by = home_id if rtype == "home_win" else away_id if rtype == "away_win" else None
        result = norm.get("result")
        matches.set_result(conn, workspace_id, actor, mid, result_type=rtype or "unknown",
                           won_by_team_id=won_by, result_raw=None if result is None else str(result))
        # classification is intentionally NOT set here — the round is a hint only (user rule).
        _set_record(conn, rec["id"], status="promoted", resolution="new", canonical_id=mid)
        created["match"] += 1

    _promote_scorecards(conn, workspace_id, actor, batch_id, created, matched)

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


def _person_by_source(conn: Connection, ref: str | None) -> UUID | None:
    """OneStats person_id for a CricketStatz PlayerID (via the people import's source identity)."""
    if ref is None:
        return None
    return conn.execute(
        text("SELECT person_id FROM person_source_identity WHERE source_system = :ss AND source_ref = :sr LIMIT 1"),
        {"ss": SOURCE_SYSTEM, "sr": ref},
    ).scalar_one_or_none()


def _canonical_by_source(conn: Connection, table: str, ref: str) -> UUID | None:
    return conn.execute(
        text(f"SELECT id FROM {table} WHERE source_system = :ss AND source_ref = :sr LIMIT 1"),
        {"ss": SOURCE_SYSTEM, "sr": ref},
    ).scalar_one_or_none()


def _promote_scorecards(
    conn: Connection, wid: UUID, actor: str, batch_id: UUID,
    created: dict[str, int], matched: dict[str, int],
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

    # innings -> innings (needs its match promoted/matched; sides linked where teams resolved)
    for rec in staged("innings"):
        norm = rec["normalised"] or {}
        existing = _canonical_by_source(conn, "innings", rec["source_ref"])
        if existing is not None:
            _set_record(conn, rec["id"], status="promoted", resolution="matched", canonical_id=existing)
            matched["innings"] += 1
            continue
        match_id = _canonical_by_source(conn, "match", norm.get("match_source_ref")) if norm.get("match_source_ref") else None
        if match_id is None:
            _flag(conn, rec["id"], "match_unresolved: innings left staged")
            continue
        bat_team = _find_canonical_by_source(conn, "team_source_identity", "team_id", norm["batting_team_source_ref"]) if norm.get("batting_team_source_ref") else None
        bowl_team = _find_canonical_by_source(conn, "team_source_identity", "team_id", norm["bowling_team_source_ref"]) if norm.get("bowling_team_source_ref") else None
        iid = innings.create_innings(
            conn, wid, actor, match_id=match_id, inns_number=norm.get("inns_number") or 1,
            batting_team_id=bat_team, bowling_team_id=bowl_team,
            byes=norm.get("byes"), legbyes=norm.get("legbyes"), wides=norm.get("wides"),
            noballs=norm.get("noballs"), iresult_raw=norm.get("iresult_raw"),
            source_system=SOURCE_SYSTEM, source_ref=rec["source_ref"],
        )
        _set_record(conn, rec["id"], status="promoted", resolution="new", canonical_id=iid)
        created["innings"] += 1

    # batting entries -> batting_entry (dismissal TYPE unresolved; raw Howout preserved)
    for rec in staged("batting_entry"):
        norm = rec["normalised"] or {}
        existing = _canonical_by_source(conn, "batting_entry", rec["source_ref"])
        if existing is not None:
            _set_record(conn, rec["id"], status="promoted", resolution="matched", canonical_id=existing)
            matched["batting_entry"] += 1
            continue
        inns_id = _canonical_by_source(conn, "innings", norm.get("innings_source_ref")) if norm.get("innings_source_ref") else None
        if inns_id is None:
            _flag(conn, rec["id"], "innings_unresolved: batting entry left staged")
            continue
        eid = batting.create_entry(
            conn, wid, actor, innings_id=inns_id,
            person_id=_person_by_source(conn, norm.get("batter_source_ref")),
            batting_position=norm.get("batting_position"), runs=norm.get("runs"),
            balls_faced=norm.get("balls_faced"), fours=norm.get("fours"), sixes=norm.get("sixes"),
            minutes=norm.get("minutes"),
            # verified CricketStatz legend; an unmapped code stays NULL (unresolved), raw code kept
            dismissal_type=map_howout(norm.get("howout_code")),
            dismissal_source_code=_s(norm.get("howout_code")),
            bowler_person_id=_person_by_source(conn, norm.get("bowler_source_ref")),
            fielder_person_id=_person_by_source(conn, norm.get("fielder_source_ref")),
            source_system=SOURCE_SYSTEM, source_ref=rec["source_ref"],
        )
        _set_record(conn, rec["id"], status="promoted", resolution="new", canonical_id=eid)
        created["batting_entry"] += 1

    # bowling entries -> bowling_entry
    for rec in staged("bowling_entry"):
        norm = rec["normalised"] or {}
        existing = _canonical_by_source(conn, "bowling_entry", rec["source_ref"])
        if existing is not None:
            _set_record(conn, rec["id"], status="promoted", resolution="matched", canonical_id=existing)
            matched["bowling_entry"] += 1
            continue
        inns_id = _canonical_by_source(conn, "innings", norm.get("innings_source_ref")) if norm.get("innings_source_ref") else None
        if inns_id is None:
            _flag(conn, rec["id"], "innings_unresolved: bowling entry left staged")
            continue
        eid = bowling.create_entry(
            conn, wid, actor, innings_id=inns_id,
            person_id=_person_by_source(conn, norm.get("bowler_source_ref")),
            bowling_order=norm.get("bowling_order"), overs_text=norm.get("overs_text"),
            maidens=norm.get("maidens"), runs_conceded=norm.get("runs_conceded"),
            wickets=norm.get("wickets"), wides=norm.get("wides"), noballs=norm.get("noballs"),
            source_system=SOURCE_SYSTEM, source_ref=rec["source_ref"],
        )
        _set_record(conn, rec["id"], status="promoted", resolution="new", canonical_id=eid)
        created["bowling_entry"] += 1

    # fall of wickets -> fall_of_wicket (factual; dismissed batter resolved where known)
    for rec in staged("fall_of_wicket"):
        norm = rec["normalised"] or {}
        existing = _canonical_by_source(conn, "fall_of_wicket", rec["source_ref"])
        if existing is not None:
            _set_record(conn, rec["id"], status="promoted", resolution="matched", canonical_id=existing)
            matched["fall_of_wicket"] += 1
            continue
        inns_id = _canonical_by_source(conn, "innings", norm.get("innings_source_ref")) if norm.get("innings_source_ref") else None
        if inns_id is None:
            _flag(conn, rec["id"], "innings_unresolved: fall of wicket left staged")
            continue
        fid = partnerships.create_fow(
            conn, wid, actor, innings_id=inns_id, wicket_number=norm.get("wicket_number"),
            team_score=norm.get("team_score"),
            dismissed_person_id=_person_by_source(conn, norm.get("dismissed_source_ref")),
            overs_text=norm.get("overs_text"),
            source_system=SOURCE_SYSTEM, source_ref=rec["source_ref"],
        )
        _set_record(conn, rec["id"], status="promoted", resolution="new", canonical_id=fid)
        created["fall_of_wicket"] += 1


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
    if people and (people.get("players") or people.get("officials")):
        pb = people_import.stage_people(conn, workspace_id, actor, payload=people, filename=filename)["batch_id"]
        out["people"]["detected"] = people_import.detect(conn, workspace_id, actor, pb)
        if commit:
            out["people"]["promoted"] = people_import.promote(conn, workspace_id, actor, pb)

    staged = parse_and_stage(conn, workspace_id, actor, payload=data, filename=filename)
    out["staged"] = staged["counts"]
    out["batch_id"] = str(staged["batch_id"])
    validate_batch(conn, workspace_id, actor, staged["batch_id"])
    out["preview"] = preview_batch(conn, staged["batch_id"])
    out["howout_unresolved"] = unresolved_howout_report(data)["unresolved_codes"]
    if commit:
        out["promoted"] = promote_batch(conn, workspace_id, actor, staged["batch_id"])
    return out


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
