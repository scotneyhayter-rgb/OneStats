"""Suggest existing persons for player names found on an internet finding (Internet Research Engine).

A finding that names players (e.g. a scorecard) gets *suggestions* of which existing people in the
workspace those names might be — so a researcher can confirm. It is strictly suggest-not-auto:

  * It NEVER merges, links or creates a person. A name is never proof of identity (the documented
    "two Bonner A are different people; D Walker / Daniel Walker are the same" lesson) — matching on a
    shared surname only raises a candidate for a human to judge.
  * Names are compared with the same ``person_resolution._normalise`` used elsewhere, plus a shared
    meaningful token (surname) test. Initials alone never match.
  * Merged-away persons are excluded (``merged_into_id IS NULL``).
"""
from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain import person_resolution

_STOP = {"the", "mr", "dr", "jr", "sr"}


def _tokens(name: str) -> set[str]:
    norm = person_resolution._normalise(name)
    return {w for w in re.sub(r"[^a-z0-9 ]", " ", norm).split() if w and w not in _STOP}


def _surname_tokens(toks: set[str]) -> set[str]:
    """Meaningful (non-initial) tokens — a real name part, not a single-letter initial."""
    return {t for t in toks if len(t) >= 3}


def load_person_index(conn: Connection, workspace_id: UUID, *, limit: int = 10000) -> list[dict[str, Any]]:
    """Load (id, display_name, token-set) for the workspace's non-merged persons, incl. historical name
    variants. Bounded so a huge workspace cannot blow up a run step."""
    rows = conn.execute(
        text("SELECT id, display_name FROM person WHERE workspace_id = :w AND merged_into_id IS NULL "
             "LIMIT :lim"),
        {"w": workspace_id, "lim": limit},
    ).mappings().all()
    index: list[dict[str, Any]] = []
    for r in rows:
        toks = _tokens(r["display_name"])
        hist = conn.execute(
            text("SELECT name FROM person_name_history WHERE person_id = :p"), {"p": r["id"]},
        ).scalars().all()
        for h in hist:
            toks |= _tokens(h)
        index.append({"person_id": str(r["id"]), "display_name": r["display_name"], "tokens": toks})
    return index


def suggest(names: list[str], person_index: list[dict[str, Any]], *, limit_per: int = 3) -> dict[str, list[dict[str, str]]]:
    """For each observed name, up to ``limit_per`` candidate persons sharing a surname token. Returns
    only names that have at least one candidate. Suggestions only — never a link or a merge."""
    out: dict[str, list[dict[str, str]]] = {}
    for name in names:
        obs = _surname_tokens(_tokens(name))
        if not obs:
            continue
        cands: list[dict[str, str]] = []
        for p in person_index:
            if obs & _surname_tokens(p["tokens"]):
                cands.append({"person_id": p["person_id"], "display_name": p["display_name"]})
            if len(cands) >= limit_per:
                break
        if cands:
            out[name] = cands
    return out
