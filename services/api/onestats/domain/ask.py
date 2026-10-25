"""Ask OneStats — natural-language statistics assistant (Phase 14, deliverable 28).

**Language in, deterministic query out.** This layer only *maps a question to a report spec* (a report in
the Phase 12 catalogue + scope filters). Every number comes from the one deterministic engine — the
assistant is a translator and presenter, never a calculator, and never invents a statistic. If a question
cannot be confidently mapped it says so and offers the nearest supported reports (deliverable 28.1/28.3,
approach 1: offline rule/grammar + synonyms; no LLM, no external service).

Guardrails (28.4): the caller's permission + workspace scope are enforced by the endpoint before this runs;
qualifications/known-minimum caveats travel with the answer; unmapped → clarify, never a guess; the same
question maps to the same report spec, so answers are reproducible.
"""
from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.reports import catalogue

# Ordered metric rules: (catalogue report id, trigger phrases). A question matches a rule when one of its
# phrases appears; the rule whose matched phrases are longest/most specific wins. Scope (finals/venue/
# season) is extracted separately and applied as a filter — never as a different report.
_RULES: list[tuple[str, list[str]]] = [
    ("bat_top_scores", ["highest score", "highest individual", "top score", "best innings", "highest innings"]),
    ("bat_most_centuries", ["most centuries", "most hundreds", "most tons"]),
    ("bat_most_fifties", ["most fifties", "most half-centuries", "most half centuries", "most 50s"]),
    ("bat_highest_average", ["best batting average", "highest batting average", "highest average", "best average with the bat"]),
    ("bat_best_strike_rate", ["best strike rate", "highest strike rate", "fastest scorer"]),
    ("bat_most_sixes", ["most sixes", "most 6s"]),
    ("bat_most_fours", ["most fours", "most 4s"]),
    ("bat_most_boundaries", ["most boundaries"]),
    ("bat_most_ducks", ["most ducks", "most noughts"]),
    ("bat_most_runs_match", ["most runs in a match", "most runs in a game"]),
    ("bat_most_runs_season", ["most runs in a season"]),
    ("bat_most_runs", ["most runs", "leading run scorer", "run scorer", "most career runs", "top run"]),
    ("bowl_most_five_fors", ["five wicket", "five-wicket", "5 wicket", "five for", "5wi", "fifer"]),
    ("bowl_best_match", ["best bowling in a match", "best bowling figures", "best figures", "best bowling"]),
    ("bowl_best_average", ["best bowling average", "lowest bowling average"]),
    ("bowl_best_economy", ["best economy", "economy rate", "most economical", "lowest economy"]),
    ("bowl_best_strike_rate", ["best bowling strike rate"]),
    ("bowl_most_maidens", ["most maidens"]),
    ("bowl_most_expensive", ["most expensive"]),
    ("bowl_most_ducks_inflicted", ["most ducks inflicted", "most ducks bowled"]),
    ("bowl_most_wickets_season", ["most wickets in a season"]),
    ("bowl_most_wickets", ["most wickets", "leading wicket taker", "wicket taker", "top wicket"]),
    ("wk_most_stumpings", ["most stumpings", "most stumped"]),
    ("wk_most_dismissals", ["most wicketkeeping dismissals", "most keeper dismissals", "most dismissals"]),
    ("wk_most_catches", ["most wicketkeeping catches", "most keeper catches"]),
    ("wk_best_innings", ["most dismissals in an innings", "best wicketkeeping in an innings"]),
    ("field_most_run_outs", ["most run outs", "most run-outs"]),
    ("field_most_catches", ["most catches", "best fielder"]),
    ("field_bowler_combos", ["fielder bowler", "fielder-bowler", "catching combination"]),
    ("capt_best_win_pct", ["winning percentage", "win percentage", "win %", "best captain", "best winning"]),
    ("capt_most_wins", ["most wins as captain", "most captaincy wins"]),
    ("capt_most_gf_wins", ["most grand finals won as captain", "most grand final wins"]),
    ("capt_most_gf", ["most grand finals captained"]),
    ("capt_consec_matches", ["most consecutive matches captained"]),
    ("capt_consec_wins", ["most consecutive wins as captain", "captaincy winning streak"]),
    ("capt_most_matches", ["most matches captained", "most games as captain", "most times captain"]),
    ("part_by_wicket", ["partnership for each wicket", "partnership by wicket", "wicket partnership"]),
    ("part_highest", ["highest partnership", "best partnership", "biggest partnership", "record partnership"]),
    ("part_aggregates", ["partnership aggregate", "most partnership runs together"]),
    ("bowl_pairs", ["best bowling pair", "bowling combination", "bowling partnership"]),
    ("team_consec_wins", ["most consecutive wins", "longest winning streak", "winning streak"]),
    ("team_unbeaten", ["unbeaten streak", "longest unbeaten"]),
    ("team_most_wins", ["most team wins", "best team"]),
    ("part_longest_serving", ["longest serving", "longest-serving", "most seasons"]),
    ("part_consec_matches", ["most consecutive matches", "most consecutive games", "longest appearance streak"]),
    ("bat_consec_no_duck", ["without a duck", "consecutive scores without a duck"]),
    ("part_matches_together", ["most matches together", "most games together", "played together"]),
    ("part_most_matches", ["most appearances", "most matches played", "most games played", "most games"]),
    ("seasonal_leaders", ["leading scorers each season", "annual leaders", "season by season leaders"]),
    ("milestones_upcoming", ["upcoming milestones", "approaching a milestone", "near a milestone"]),
    ("honours_all", ["life members", "honours", "awards", "best and fairest"]),
]

# captaincy context: when a streak question mentions the captain, prefer the captaincy streak report
_CAPTAIN_WORDS = ("captain", "skipper")


def _best_rule(q: str) -> tuple[str, int]:
    best_id, best_score = "", 0
    for rid, phrases in _RULES:
        score = max((len(p) for p in phrases if p in q), default=0)
        if score > best_score:
            best_id, best_score = rid, score
    return best_id, best_score


def _scope(conn: Connection, workspace_id: UUID, q: str) -> tuple[dict[str, Any], list[str]]:
    filters: dict[str, Any] = {"workspace_id": workspace_id}
    labels: list[str] = []
    if "grand final" in q:
        filters["split"] = "grand_final"
        labels.append("Grand Finals only")
    elif re.search(r"\bfinals?\b", q) and "grand" not in q:
        filters["split"] = "finals"
        labels.append("Finals only")
    if re.search(r"\bat home\b|\bhome matches\b", q):
        filters["venue"] = "home"
        labels.append("Home matches")
    elif re.search(r"\baway\b", q):
        filters["venue"] = "away"
        labels.append("Away matches")
    # season label (e.g. 2024/25) mentioned in the question → restrict to that season
    for r in conn.execute(text("SELECT id, label FROM season WHERE workspace_id = :w"), {"w": workspace_id}).mappings():
        if r["label"] and r["label"].lower() in q:
            filters["season_id"] = r["id"]
            labels.append(f"Season {r['label']}")
            break
    return filters, labels


def _suggestions(q: str, limit: int = 5) -> list[dict[str, str]]:
    words = {w for w in re.findall(r"[a-z]+", q) if len(w) > 2}
    scored = []
    for e in catalogue.CATALOGUE:
        hay = (e.name + " " + e.description + " " + e.category).lower()
        overlap = sum(1 for w in words if w in hay)
        if overlap:
            scored.append((overlap, e))
    scored.sort(key=lambda t: -t[0])
    return [{"id": e.id, "name": e.name, "category": e.category} for _s, e in scored[:limit]]


def answer(conn: Connection, workspace_id: UUID, question: str, *, top: int = 10) -> dict[str, Any]:
    """Map the question to a catalogue report + scope, run it on the engine, and present the answer with
    its interpretation and qualifications. Never fabricates: an unmapped question returns suggestions."""
    q = " ".join((question or "").lower().split())
    if not q:
        return {"question": question, "matched": False, "message": "Please ask a question.", "suggestions": []}

    rid, score = _best_rule(q)
    # captaincy disambiguation for streaks phrased about the captain
    if rid == "team_consec_wins" and any(w in q for w in _CAPTAIN_WORDS):
        rid = "capt_consec_wins"
    if not rid or score == 0:
        return {"question": question, "matched": False,
                "message": ("I can only answer from verified statistics I can map to a report. I couldn't "
                            "confidently map that question — here are the closest reports."),
                "suggestions": _suggestions(q)}

    entry = catalogue.CAT_BY_ID[rid]
    filters, scope_labels = _scope(conn, workspace_id, q)
    data = catalogue.report_rows(conn, workspace_id, rid, filters, limit=max(top, 10))
    rows = data["rows"][:top]
    quals = [n for n in (entry.qualification, entry.limitations) if n]
    quals.append("Figures are from approved scorecards only; unknown values are never treated as zero.")
    interpretation = f"I read this as the “{entry.name}” report"
    if scope_labels:
        interpretation += " (" + ", ".join(scope_labels) + ")"
    interpretation += "."
    return {
        "question": question, "matched": True, "confidence": "high" if score >= 8 else "medium",
        "report_id": rid, "report_name": entry.name, "category": entry.category,
        "interpretation": interpretation, "scope": scope_labels,
        "columns": data["columns"], "rows": rows, "qualifications": quals,
        "answer_summary": _summarise(rows, data["columns"]),
    }


def _summarise(rows: list[dict[str, Any]], columns: list[dict[str, Any]]) -> str | None:
    """A one-line plain-language headline from the No. 1 row (names/values straight from the engine)."""
    if not rows:
        return "No verified data matches that question yet."
    top = rows[0]
    name = top.get("player") or top.get("team") or top.get("player1_name") or top.get("members_names")
    # the first non-rank, non-name numeric column is the headline value
    value = None
    for c in columns:
        if c["key"] in ("rank", "player", "team", "team_name", "player1_name", "player2_name",
                        "members_names", "season", "start_date", "end_date", "match_date"):
            continue
        v = top.get(c["key"])
        if v is not None:
            value = f"{v} {c['label']}"
            break
    if name and value:
        return f"{name} leads: {value}."
    return None
