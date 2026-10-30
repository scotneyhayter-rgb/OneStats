"""Historical Research Timeline — season coverage (Phase 10, Stage 10.12).

A transparent, evidence-based view of what is covered across a workspace's full history. Metrics are
COMPUTED from real match data; the computed class is capped at 'partial' and never claims
'comprehensive' from counts alone (absence of a fixture list is Unassessed, not Comprehensive). An
explicit, evidence-backed assessment (season_coverage) can raise a season to 'comprehensive' or mark it
'inactive' (demonstrably no cricket) — distinct from 'unassessed' (no surviving evidence). The
methodology/thresholds are returned with the data so the user can see how each class was derived.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain import audit

ASSESSED_CLASSES = ("comprehensive", "partial", "significant_gaps", "unassessed", "inactive")

# Documented, configurable thresholds (returned to the user). Computed classification never asserts
# 'comprehensive' — that requires explicit coverage evidence via an assessment.
METHODOLOGY = {
    "verified_share_for_partial": 0.0,   # any verified records -> at least 'partial'
    "note": ("Computed from recorded matches and their verification status. A season with no known "
             "matches is 'unassessed' (absence of records is not absence of cricket). Computed classes "
             "are capped at 'partial'; 'comprehensive' and 'inactive' require an explicit, evidence-backed "
             "assessment. Completeness and verification are distinct axes."),
}


def classify_computed(total: int, verified: int) -> str:
    """Honest, counts-only classification — never 'comprehensive'."""
    if total == 0:
        return "unassessed"
    if verified == 0:
        return "significant_gaps"
    return "partial"


def season_timeline(conn: Connection, workspace_id: UUID, *, competition_id: UUID | None = None) -> dict[str, Any]:
    params: dict[str, Any] = {"w": workspace_id}
    comp_filter = ""
    if competition_id is not None:
        comp_filter = " AND s.competition_id = :c"
        params["c"] = competition_id
    rows = conn.execute(
        text(
            "SELECT s.id AS season_id, s.label, s.competition_id, s.start_date, s.end_date, "
            "  count(m.id) AS total, "
            "  count(m.id) FILTER (WHERE m.approval_status IN ('approved','verified_partial')) AS verified, "
            "  count(m.id) FILTER (WHERE m.approval_status = 'disputed') AS disputed, "
            "  count(m.id) FILTER (WHERE m.approval_status = 'draft') AS draft, "
            "  count(m.id) FILTER (WHERE m.result_type IS NULL OR m.result_type = 'unknown') AS no_result, "
            "  count(m.id) FILTER (WHERE m.match_date IS NULL) AS unknown_date "
            "FROM season s LEFT JOIN match m ON m.season_id = s.id AND m.workspace_id = s.workspace_id "
            f"WHERE s.workspace_id = :w{comp_filter} "
            "GROUP BY s.id, s.label, s.competition_id, s.start_date, s.end_date "
            "ORDER BY s.start_date NULLS LAST, s.label"
        ),
        params,
    ).mappings().all()

    overrides = {
        (r["season_id"], r["competition_id"], r["grade_id"]): r
        for r in conn.execute(
            text("SELECT season_id, competition_id, grade_id, assessed_class, basis FROM season_coverage "
                 "WHERE workspace_id = :w"), {"w": workspace_id}).mappings().all()
    }

    seasons = []
    for r in rows:
        total, verified = r["total"], r["verified"]
        computed = classify_computed(total, verified)
        override = overrides.get((r["season_id"], r["competition_id"], None)) or \
            overrides.get((r["season_id"], None, None))
        seasons.append({
            "season_id": str(r["season_id"]),
            "label": r["label"],
            "competition_id": str(r["competition_id"]) if r["competition_id"] else None,
            "start_date": r["start_date"].isoformat() if r["start_date"] else None,
            "end_date": r["end_date"].isoformat() if r["end_date"] else None,
            "total_matches": total,
            "verified_matches": verified,
            "disputed_matches": r["disputed"],
            "draft_matches": r["draft"],
            "matches_without_result": r["no_result"],
            "matches_unknown_date": r["unknown_date"],
            "computed_class": computed,
            "assessed_class": override["assessed_class"] if override else None,
            "coverage_class": override["assessed_class"] if override else computed,
            "assessment_basis": override["basis"] if override else None,
        })
    return {"seasons": seasons, "methodology": METHODOLOGY}


def set_assessment(conn: Connection, workspace_id: UUID, actor: str, *, season_id: UUID, assessed_class: str,
                   competition_id: UUID | None = None, grade_id: UUID | None = None,
                   basis: str | None = None) -> dict[str, Any]:
    """Record an explicit, evidence-backed coverage assessment for a season (the only way to a
    'comprehensive' or 'inactive' classification)."""
    if assessed_class not in ASSESSED_CLASSES:
        raise ValueError("invalid_assessed_class")
    cid = conn.execute(
        text("INSERT INTO season_coverage(workspace_id, season_id, competition_id, grade_id, assessed_class, "
             "basis, assessed_by) VALUES (:w, :s, :c, :g, :cls, :b, :by) "
             "ON CONFLICT ON CONSTRAINT uq_season_coverage DO UPDATE SET assessed_class = :cls, basis = :b, "
             "assessed_by = :by, updated_at = now() RETURNING id"),
        {"w": workspace_id, "s": season_id, "c": competition_id, "g": grade_id, "cls": assessed_class,
         "b": basis, "by": actor},
    ).scalar_one()
    audit.write_audit(conn, workspace_id, actor, "research.coverage_assessed", entity="season_coverage",
                      entity_id=str(cid), after={"season_id": str(season_id), "assessed_class": assessed_class})
    r = conn.execute(text("SELECT * FROM season_coverage WHERE id = :id"), {"id": cid}).mappings().first()
    return dict(r)


# --- Season completeness (Research Centre redesign) -------------------------------------------------
# Four DISTINCT axes, never conflated into one misleading percentage (Stage 3):
#  * Fixture coverage  — known matches vs INDEPENDENTLY ESTABLISHED expected fixtures. Expected fixtures
#    are not derived from the matches already entered, so this is "Coverage Unknown" until a researcher
#    records an evidence-backed assessment. A season can have complete scorecards for every KNOWN match and
#    still have unknown fixture coverage.
#  * Scorecard completeness — of the KNOWN matches, how many carry a scorecard (innings recorded).
#  * Verification — of the known matches, how many are approved/verified.
#  * Research coverage — whether sources/research have actually been recorded for the season.
COMPLETENESS_STATUSES = ("verified", "needs_attention", "incomplete", "not_researched",
                         "coverage_unknown", "conflicting_evidence")


def _completeness_status(known: int, with_card: int, verified: int, disputed: int, draft: int,
                         no_result: int, researched: bool, assessed_class: str | None) -> tuple[str, list[str]]:
    """The single most useful status plus the full list of underlying issues (nothing hidden)."""
    issues: list[str] = []
    if disputed:
        issues.append("conflicting_evidence")
    if known - with_card > 0:
        issues.append("missing_scorecards")
    if no_result > 0:
        issues.append("missing_results")
    if draft > 0:
        issues.append("unverified_scorecards")
    if assessed_class is None:
        issues.append("fixture_coverage_unknown")
    # primary status, most-serious first
    if known == 0:
        primary = "not_researched" if not researched else "coverage_unknown"
    elif disputed:
        primary = "conflicting_evidence"
    elif (known - with_card) > 0 or draft > 0 or no_result > 0:
        primary = "incomplete"
    elif assessed_class == "comprehensive" and verified == known:
        primary = "verified"
    elif assessed_class is None:
        primary = "coverage_unknown"      # every known match is fine, but we don't know all fixtures are present
    else:
        primary = "needs_attention"
    return primary, issues


def season_completeness(conn: Connection, workspace_id: UUID, *, competition_id: UUID | None = None,
                        grade_id: UUID | None = None) -> dict[str, Any]:
    """Per-season completeness across the four axes, for the Research Centre's graphical overview. Honest
    by construction: unknown fixture coverage is reported as such, never as 100%."""
    params: dict[str, Any] = {"w": workspace_id}
    where = ""
    if competition_id is not None:
        where += " AND s.competition_id = :c"; params["c"] = competition_id
    rows = conn.execute(
        text(
            "SELECT s.id AS season_id, s.label, s.competition_id, s.start_date, s.end_date, "
            "  count(m.id) AS known, "
            "  count(m.id) FILTER (WHERE EXISTS (SELECT 1 FROM innings i WHERE i.match_id = m.id)) AS with_card, "
            "  count(m.id) FILTER (WHERE m.approval_status IN ('approved','verified_partial')) AS verified, "
            "  count(m.id) FILTER (WHERE m.approval_status = 'disputed') AS disputed, "
            "  count(m.id) FILTER (WHERE m.approval_status = 'draft') AS draft, "
            "  count(m.id) FILTER (WHERE m.result_type IS NULL OR m.result_type = 'unknown') AS no_result "
            "FROM season s LEFT JOIN match m ON m.season_id = s.id AND m.workspace_id = s.workspace_id "
            f"WHERE s.workspace_id = :w{where} "
            "GROUP BY s.id, s.label, s.competition_id, s.start_date, s.end_date "
            "ORDER BY s.start_date NULLS LAST, s.label"
        ), params,
    ).mappings().all()
    assessed = {r["season_id"]: r["assessed_class"] for r in conn.execute(
        text("SELECT season_id, assessed_class FROM season_coverage WHERE workspace_id = :w"),
        {"w": workspace_id}).mappings().all()}
    researched_seasons = {r[0] for r in conn.execute(
        text("SELECT DISTINCT m.season_id FROM research_source_match rsm "
             "JOIN match m ON m.id = rsm.match_id WHERE rsm.workspace_id = :w AND m.season_id IS NOT NULL"),
        {"w": workspace_id})}
    out = []
    for r in rows:
        known, with_card = r["known"], r["with_card"]
        ass = assessed.get(r["season_id"])
        researched = r["season_id"] in researched_seasons or ass is not None
        status, issues = _completeness_status(known, with_card, r["verified"], r["disputed"], r["draft"],
                                              r["no_result"], researched, ass)
        out.append({
            "season_id": str(r["season_id"]), "label": r["label"],
            "competition_id": str(r["competition_id"]) if r["competition_id"] else None,
            "start_date": r["start_date"].isoformat() if r["start_date"] else None,
            "end_date": r["end_date"].isoformat() if r["end_date"] else None,
            "known_matches": known,
            "with_scorecard": with_card,
            "missing_scorecards": known - with_card,
            "verified_matches": r["verified"],
            "missing_results": r["no_result"],
            "draft_matches": r["draft"],
            "disputed_matches": r["disputed"],
            # scorecard completeness is OVER KNOWN MATCHES only, and null when nothing is known
            "scorecard_completeness_pct": round(with_card * 100 / known) if known else None,
            "verification_pct": round(r["verified"] * 100 / known) if known else None,
            # fixture coverage stays unknown until an evidence-backed assessment establishes the expected
            # fixtures — never inferred from the entered matches (Stage 3)
            "fixture_coverage": "established" if ass == "comprehensive" else "unknown",
            "assessed_class": ass,
            "research_recorded": researched,
            "status": status,
            "issues": issues,
        })
    return {"seasons": out, "methodology": METHODOLOGY, "statuses": list(COMPLETENESS_STATUSES)}
