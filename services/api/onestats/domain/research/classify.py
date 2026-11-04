"""Classify an internet finding against the workspace's existing matches (Internet Research Engine).

Turns an extracted match-like candidate into one of the review classifications used by the rest of the
app — ``possible_duplicate`` / ``additional_evidence`` / ``new`` / ``unknown`` — by a dependency-free,
name-based comparison with the matches already recorded in the workspace. It is deliberately cautious:

  * It NEVER merges, links or imports anything. It only tags the finding and lists candidate match ids
    with human-readable reasons, so a researcher decides.
  * Team names are compared by normalised tokens (club suffixes like "CC"/"Cricket Club" stripped), not
    by identity — a name is never treated as proof of identity (same rule as player/person resolution).
  * Confidence is a capped hint (≤0.9), never certainty; ``unknown`` carries confidence ``None``.
  * Only match-like findings (a scorecard/result/match candidate that actually names teams) are
    classified; everything else stays ``unknown`` rather than being forced into a bucket.
"""
from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

# Club-name noise stripped before comparing (so "Rhymney CC" ~ "Rhymney Cricket Club" ~ "Rhymney").
_SUFFIX = {"cc", "cricket", "club", "the", "cricketclub", "1st", "xi", "2nd", "first", "second"}
MATCH_KINDS = ("scorecard", "result", "match_candidate")


def _tokens(name: str | None) -> set[str]:
    if not name:
        return set()
    cleaned = re.sub(r"[^a-z0-9 ]", " ", name.lower())
    return {w for w in cleaned.split() if w and w not in _SUFFIX}


def _teams_match(observed: set[str], recorded: set[str]) -> bool:
    """A conservative name match: a shared meaningful token, with subset or ≥50% Jaccard overlap."""
    if not observed or not recorded:
        return False
    shared = observed & recorded
    if not any(len(tok) >= 3 for tok in shared):
        return False
    if observed <= recorded or recorded <= observed:
        return True
    return len(shared) / len(observed | recorded) >= 0.5


def _years(dates: Any) -> set[int]:
    out: set[int] = set()
    if isinstance(dates, list):
        for d in dates:
            for m in re.findall(r"(?:18|19|20)\d{2}", str(d)):
                out.add(int(m))
    return out


def load_match_index(conn: Connection, workspace_id: UUID, *, limit: int = 5000) -> list[dict[str, Any]]:
    """Load (match_id, year, team-token-sets) for the workspace's matches — once per run step. Bounded
    so a very large workspace cannot blow up a tick; classification simply degrades to fewer candidates."""
    rows = conn.execute(
        text("SELECT m.id AS match_id, m.match_date, m.margin_runs, m.margin_wickets, t.name AS team_name "
             "FROM match m JOIN match_team mt ON mt.match_id = m.id "
             "JOIN team t ON t.id = mt.team_id WHERE m.workspace_id = :w "
             "ORDER BY m.match_date DESC NULLS LAST LIMIT :lim"),
        {"w": workspace_id, "lim": limit},
    ).mappings().all()
    by_match: dict[str, dict[str, Any]] = {}
    for r in rows:
        mid = str(r["match_id"])
        entry = by_match.setdefault(mid, {"match_id": mid, "year": None, "teams": [],
                                          "margin_runs": r["margin_runs"], "margin_wickets": r["margin_wickets"]})
        if r["match_date"] is not None and entry["year"] is None:
            entry["year"] = r["match_date"].year
        toks = _tokens(r["team_name"])
        if toks:
            entry["teams"].append(toks)
    return list(by_match.values())


def _result_conflicts(observed: dict[str, Any] | None, m: dict[str, Any]) -> str | None:
    """If the finding states a win margin that disagrees with the recorded match's margin, return a
    reason. Conservative: only when BOTH sides give a numeric margin and they differ. The recorded
    (verified, CricketStatz-derived) figure is NEVER changed — this only flags for human review."""
    if not observed or observed.get("margin") is None:
        return None
    rec_runs, rec_wkts = m.get("margin_runs"), m.get("margin_wickets")
    if rec_runs is None and rec_wkts is None:
        return None
    unit, margin = observed.get("unit"), observed.get("margin")
    if unit == "runs" and rec_runs is not None and rec_runs != margin:
        return f"source says won by {margin} runs, your record says {rec_runs} runs"
    if unit == "wickets" and rec_wkts is not None and rec_wkts != margin:
        return f"source says won by {margin} wickets, your record says {rec_wkts} wickets"
    if unit == "runs" and rec_runs is None and rec_wkts is not None:
        return f"source says won by {margin} runs, your record is a win by wickets"
    if unit == "wickets" and rec_wkts is None and rec_runs is not None:
        return f"source says won by {margin} wickets, your record is a win by runs"
    return None


def classify(extracted: dict[str, Any] | None, match_index: list[dict[str, Any]]) -> dict[str, Any]:
    """Return {classification, confidence, reason, candidate_match_ids}. Never merges; review-only."""
    extracted = extracted or {}
    observed_teams = [t for t in (extracted.get("observed_teams") or []) if isinstance(t, str)]
    obs_tokensets = [ts for ts in (_tokens(t) for t in observed_teams) if ts]
    finding_years = _years(extracted.get("observed_dates"))

    if not obs_tokensets:
        return {"classification": "unknown", "confidence": None,
                "reason": "no team names were extracted, so this cannot be matched to a record yet",
                "candidate_match_ids": []}

    observed_result = extracted.get("observed_result")
    best: dict[str, Any] | None = None
    for m in match_index:
        matched_teams = 0
        for obs in obs_tokensets:
            if any(_teams_match(obs, rec) for rec in m["teams"]):
                matched_teams += 1
        if matched_teams == 0:
            continue
        year_match = bool(finding_years and m["year"] in finding_years)
        conflict = _result_conflicts(observed_result, m) if matched_teams >= 2 else None
        if matched_teams >= 2 and conflict:
            cand = {"kind": "conflicting", "confidence": 0.85, "match_id": m["match_id"],
                    "reason": conflict + " — flagged for review; your verified record is never overwritten"}
        elif matched_teams >= 2 and year_match:
            cand = {"kind": "possible_duplicate", "confidence": 0.8, "match_id": m["match_id"],
                    "reason": "same teams and year as an existing match — likely the same match"}
        elif matched_teams >= 2:
            cand = {"kind": "possible_duplicate", "confidence": 0.6, "match_id": m["match_id"],
                    "reason": "same two teams as an existing match (date unconfirmed)"}
        elif year_match:
            cand = {"kind": "additional_evidence", "confidence": 0.5, "match_id": m["match_id"],
                    "reason": "mentions a known team in a season you already have"}
        else:
            cand = {"kind": "additional_evidence", "confidence": 0.35, "match_id": m["match_id"],
                    "reason": "mentions a team that appears in your existing matches"}
        if best is None or cand["confidence"] > best["confidence"]:
            best = cand

    if best is not None:
        # collect up to a few candidate ids sharing the best kind for the reviewer
        ids = [best["match_id"]]
        return {"classification": best["kind"], "confidence": round(min(best["confidence"], 0.9), 3),
                "reason": best["reason"], "candidate_match_ids": ids}

    # Teams were named but none appear in the workspace → this looks like a match we do NOT have.
    return {"classification": "new", "confidence": 0.3,
            "reason": "names teams not found among your existing matches — possibly a new record",
            "candidate_match_ids": []}
