"""Person identity resolution — evidence-based duplicate detection & reversible merging
(Phase 5, Stage 3).

Protects the integrity of historical statistics. A matching name **never** establishes identity:
the detector surfaces *candidates* with explicit evidence and a confidence, and only an
administrator decides. Merges are reversible and never delete the merged record, its source
references, affiliations or evidence; statistics resolve through the surviving (canonical)
identity, so a merge removes double counting without rewriting history. "Definitely different"
assertions (two different A Bonner) are preserved and block future merges/suggestions. A review
queue holds competing possibilities (J Smith / Smith / J. Smith / John Smith) without ever
auto-merging.

Workspace-scoped (RLS); governed by ``person.manage``; every decision audited.
"""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain import affiliations, audit, people

_MAX_CHAIN = 64
REVIEW_STATUSES = ("pending", "merged", "distinct", "deferred", "rejected")


def _normalise(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def _ordered(a: UUID, b: UUID) -> tuple[UUID, UUID]:
    return (a, b) if str(a) <= str(b) else (b, a)


# --------------------------------------------------------------- distinct assertions


def are_asserted_distinct(conn: Connection, a: UUID, b: UUID) -> bool:
    x, y = _ordered(a, b)
    return conn.execute(
        text("SELECT 1 FROM person_distinct_assertion WHERE person_a_id = :a AND person_b_id = :b"),
        {"a": x, "b": y},
    ).first() is not None


def assert_distinct(
    conn: Connection, workspace_id: UUID, actor: str, a: UUID, b: UUID, *,
    reason: str | None = None, evidence: str | None = None,
) -> UUID:
    if a == b:
        raise ValueError("same_person")
    for pid in (a, b):
        if people.get_person(conn, pid, include_protected=True) is None:
            raise ValueError("person_not_found")
    x, y = _ordered(a, b)
    existing = conn.execute(
        text("SELECT id FROM person_distinct_assertion WHERE person_a_id = :a AND person_b_id = :b"),
        {"a": x, "b": y},
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    aid = conn.execute(
        text(
            "INSERT INTO person_distinct_assertion(workspace_id, person_a_id, person_b_id, actor, reason, evidence) "
            "VALUES (:w, :a, :b, :actor, :reason, :ev) RETURNING id"
        ),
        {"w": workspace_id, "a": x, "b": y, "actor": actor, "reason": reason, "ev": evidence},
    ).scalar_one()
    audit.write_audit(conn, workspace_id, actor, "person.assert_distinct", entity="person",
                      entity_id=str(x), after={"person_a_id": str(x), "person_b_id": str(y), "reason": reason})
    return aid


# --------------------------------------------------------------- detection


def _affiliation_orgs(conn: Connection, person_id: UUID) -> set[UUID]:
    return set(conn.execute(
        text("SELECT DISTINCT organisation_id FROM person_affiliation WHERE person_id = :p"),
        {"p": person_id},
    ).scalars().all())


def find_duplicate_candidates(conn: Connection, person_id: UUID) -> list[dict[str, Any]]:
    """Evidence-based candidate suggestions for ``person_id``. Evidence (strongest first):
    a shared external source identity; an identical normalised name/alias; a shared initials/
    surname form; and a **shared club affiliation** as corroborating (not sole) evidence. A name
    or initials match alone is only ever weak and never proof. Already-merged people and pairs
    asserted distinct are excluded."""
    person = people.get_person(conn, person_id, include_protected=True)
    if person is None:
        raise ValueError("person_not_found")

    candidates: dict[UUID, set[str]] = {}

    def add(pid: UUID, ev: str) -> None:
        candidates.setdefault(pid, set()).add(ev)

    # Shared source identity (strong) — note the UNIQUE source-ref constraint makes this rare
    # in-workspace, but it is honoured when it occurs (e.g. relaxed/historical data).
    for pid in conn.execute(
        text(
            "SELECT DISTINCT o.person_id FROM person_source_identity m "
            "JOIN person_source_identity o ON o.source_system = m.source_system AND o.source_ref = m.source_ref "
            "WHERE m.person_id = :p AND o.person_id <> :p"
        ),
        {"p": person_id},
    ).scalars().all():
        add(pid, "shared_source_identity")

    # Name / alias / initials matches across all recorded names of both people (weak).
    my_names = conn.execute(
        text("SELECT name FROM person_name_history WHERE person_id = :p"), {"p": person_id}
    ).scalars().all()
    norm_keys = {_normalise(person["display_name"]), *(_normalise(n) for n in my_names)}
    norm_keys.discard("")
    if norm_keys:
        rows = conn.execute(
            text(
                "SELECT DISTINCT p.id FROM person p "
                "LEFT JOIN person_name_history nh ON nh.person_id = p.id "
                "WHERE p.id <> :self AND p.merged_into_id IS NULL AND ("
                "  regexp_replace(lower(btrim(p.display_name)), '\\s+', ' ', 'g') = ANY(:keys) "
                "  OR regexp_replace(lower(btrim(nh.name)), '\\s+', ' ', 'g') = ANY(:keys))"
            ),
            {"self": person_id, "keys": list(norm_keys)},
        ).scalars().all()
        for pid in rows:
            add(pid, "name_or_alias_match")

    # Shared club affiliation — corroborating evidence only.
    my_orgs = _affiliation_orgs(conn, person_id)
    results: list[dict[str, Any]] = []
    for pid, evidence in candidates.items():
        if are_asserted_distinct(conn, person_id, pid):
            continue
        cand = people.get_person(conn, pid, include_protected=False)
        if cand is None or cand["merged_into_id"] is not None:
            continue
        if my_orgs and (my_orgs & _affiliation_orgs(conn, pid)):
            evidence.add("shared_club_affiliation")
        strong = "shared_source_identity" in evidence
        # A name match corroborated by a shared club is "medium"; name alone stays "weak".
        medium = (not strong) and "name_or_alias_match" in evidence and "shared_club_affiliation" in evidence
        results.append({
            "person_id": pid, "display_name": cand["display_name"], "evidence": sorted(evidence),
            "confidence": "strong" if strong else ("medium" if medium else "weak"),
        })
    order = {"strong": 0, "medium": 1, "weak": 2}
    results.sort(key=lambda r: (order[r["confidence"]], r["display_name"]))
    return results


def scan_duplicate_pairs(conn: Connection, workspace_id: UUID) -> list[dict[str, Any]]:
    """Workspace-wide duplicate candidate PAIRS for the identity review worklist — so cross-club
    players (the same person under two clubs' records) can be resolved from one list instead of
    opening every profile. Evidence: a shared external source identity is **strong**; an identical
    normalised name/alias is **weak**, upgraded to **medium** when the pair also shares a club
    affiliation. Already-merged people and pairs asserted distinct are excluded. Deduped, sorted
    strongest-first. A name/initials match alone is never proof — these are suggestions to review."""
    pairs: dict[tuple[UUID, UUID], set[str]] = {}

    def add(a: UUID, b: UUID, ev: str) -> None:
        if a == b:
            return
        pairs.setdefault(_ordered(a, b), set()).add(ev)

    # strong: two live people sharing an external source identity
    for r in conn.execute(text(
        "SELECT a.person_id AS pa, b.person_id AS pb FROM person_source_identity a "
        "JOIN person_source_identity b ON a.source_system = b.source_system "
        "  AND a.source_ref = b.source_ref AND a.person_id < b.person_id "
        "JOIN person pa ON pa.id = a.person_id AND pa.merged_into_id IS NULL "
        "JOIN person pb ON pb.id = b.person_id AND pb.merged_into_id IS NULL"
    )).mappings().all():
        add(r["pa"], r["pb"], "shared_source_identity")

    # weak: two live people sharing an identical normalised name/alias (display name or name history)
    for r in conn.execute(text(
        "WITH names AS ("
        "  SELECT p.id AS person_id, regexp_replace(lower(btrim(p.display_name)), '\\s+', ' ', 'g') AS k "
        "    FROM person p WHERE p.merged_into_id IS NULL "
        "  UNION "
        "  SELECT nh.person_id, regexp_replace(lower(btrim(nh.name)), '\\s+', ' ', 'g') AS k "
        "    FROM person_name_history nh JOIN person p ON p.id = nh.person_id AND p.merged_into_id IS NULL) "
        "SELECT a.person_id AS pa, b.person_id AS pb FROM names a "
        "JOIN names b ON a.k = b.k AND a.person_id < b.person_id WHERE a.k <> ''"
    )).mappings().all():
        add(r["pa"], r["pb"], "name_or_alias_match")

    if not pairs:
        return []

    involved = sorted({p for pair in pairs for p in pair}, key=str)
    orgs: dict[UUID, set[UUID]] = {p: set() for p in involved}
    for r in conn.execute(
        text("SELECT person_id, organisation_id FROM person_affiliation WHERE person_id = ANY(CAST(:ids AS uuid[]))"),
        {"ids": involved},
    ).mappings().all():
        orgs.setdefault(r["person_id"], set()).add(r["organisation_id"])
    names = {r["id"]: r["display_name"] for r in conn.execute(
        text("SELECT id, display_name FROM person WHERE id = ANY(CAST(:ids AS uuid[]))"),
        {"ids": involved},
    ).mappings().all()}

    out: list[dict[str, Any]] = []
    for (a, b), evidence in pairs.items():
        if are_asserted_distinct(conn, a, b):
            continue
        if orgs.get(a) and (orgs[a] & orgs.get(b, set())):
            evidence.add("shared_club_affiliation")
        strong = "shared_source_identity" in evidence
        medium = (not strong) and "name_or_alias_match" in evidence and "shared_club_affiliation" in evidence
        out.append({
            "person_a_id": a, "person_b_id": b,
            "a_display_name": names.get(a), "b_display_name": names.get(b),
            "evidence": sorted(evidence),
            "confidence": "strong" if strong else ("medium" if medium else "weak"),
        })
    order = {"strong": 0, "medium": 1, "weak": 2}
    out.sort(key=lambda r: (order[r["confidence"]], r["a_display_name"] or "", r["b_display_name"] or ""))
    return out


def compare(conn: Connection, a: UUID, b: UUID) -> dict[str, Any]:
    """Side-by-side data for administrator review: both records, names, source identities,
    affiliations, and whether they are already asserted distinct or merged."""
    pa = people.detail(conn, a, include_protected=True)
    pb = people.detail(conn, b, include_protected=True)
    if pa is None or pb is None:
        raise ValueError("person_not_found")
    pa["affiliations"] = affiliations.list_affiliations(conn, person_id=a)
    pb["affiliations"] = affiliations.list_affiliations(conn, person_id=b)
    return {"a": pa, "b": pb, "asserted_distinct": are_asserted_distinct(conn, a, b)}


# --------------------------------------------------------------- merge / undo


def resolve_canonical(conn: Connection, person_id: UUID) -> UUID:
    current = person_id
    for _ in range(_MAX_CHAIN):
        nxt = conn.execute(
            text("SELECT merged_into_id FROM person WHERE id = :id"), {"id": current}
        ).scalar_one_or_none()
        if nxt is None:
            return current
        current = nxt
    raise ValueError("merge_chain_too_deep")


def merge_people(
    conn: Connection, workspace_id: UUID, actor: str, canonical_id: UUID, merged_id: UUID, *,
    reason: str | None = None, evidence: str | None = None,
) -> dict[str, Any]:
    """Administrator-approved, reversible merge of ``merged_id`` into ``canonical_id``. Nothing is
    deleted; the merged record keeps its own identifiers, source references, names and affiliations
    and is simply pointed at the canonical record. Guards against self-merge, already-merged
    records, asserted-distinct pairs and circular merges."""
    if canonical_id == merged_id:
        raise ValueError("cannot_merge_same")
    canonical = people.get_person(conn, canonical_id, include_protected=True)
    merged = people.get_person(conn, merged_id, include_protected=True)
    if canonical is None or merged is None:
        raise ValueError("person_not_found")
    if canonical["merged_into_id"] is not None:
        raise ValueError("canonical_already_merged")
    if merged["merged_into_id"] is not None:
        raise ValueError("already_merged")
    if are_asserted_distinct(conn, canonical_id, merged_id):
        raise ValueError("asserted_distinct")
    # Circular-merge guard: the canonical's own chain must not lead back to the merged record.
    if resolve_canonical(conn, canonical_id) == merged_id:
        raise ValueError("circular_merge")

    conn.execute(
        text("UPDATE person SET merged_into_id = :c, status = 'merged' WHERE id = :m"),
        {"c": canonical_id, "m": merged_id},
    )
    merge_id = conn.execute(
        text(
            "INSERT INTO person_merge(workspace_id, canonical_person_id, merged_person_id, actor, reason, evidence) "
            "VALUES (:w, :c, :m, :actor, :reason, :ev) RETURNING id"
        ),
        {"w": workspace_id, "c": canonical_id, "m": merged_id, "actor": actor, "reason": reason, "ev": evidence},
    ).scalar_one()
    audit.write_audit(conn, workspace_id, actor, "person.merge", entity="person", entity_id=str(merged_id),
                      after={"canonical_person_id": str(canonical_id), "merged_person_id": str(merged_id),
                             "reason": reason})
    return {"merge_id": merge_id, "canonical_person_id": canonical_id, "merged_person_id": merged_id}


def undo_merge(conn: Connection, workspace_id: UUID, actor: str, merge_id: UUID) -> dict[str, Any]:
    """Reverse a merge, restoring the merged person as an independent record. Subsequent legitimate
    changes to either record are untouched — only the merge pointer is cleared."""
    row = conn.execute(
        text("SELECT id, merged_person_id, is_undone FROM person_merge WHERE id = :id"), {"id": merge_id}
    ).mappings().first()
    if row is None:
        raise ValueError("merge_not_found")
    if row["is_undone"]:
        raise ValueError("already_undone")
    merged_id = row["merged_person_id"]
    conn.execute(
        text("UPDATE person SET merged_into_id = NULL, status = 'active' WHERE id = :m"), {"m": merged_id}
    )
    conn.execute(
        text("UPDATE person_merge SET is_undone = true, undone_at = now(), undone_by = :actor WHERE id = :id"),
        {"actor": actor, "id": merge_id},
    )
    audit.write_audit(conn, workspace_id, actor, "person.merge.undo", entity="person",
                      entity_id=str(merged_id), after={"merge_id": str(merge_id)})
    return {"merge_id": merge_id, "merged_person_id": merged_id, "undone": True}


def list_merges(conn: Connection, *, person_id: UUID | None = None, include_undone: bool = True) -> list[dict[str, Any]]:
    sql = ("SELECT id, canonical_person_id, merged_person_id, actor, reason, evidence, at, "
           "is_undone, undone_at, undone_by FROM person_merge")
    clauses, params = [], {}
    if person_id is not None:
        clauses.append("(canonical_person_id = :p OR merged_person_id = :p)")
        params["p"] = person_id
    if not include_undone:
        clauses.append("is_undone = false")
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY at DESC"
    return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]


# --------------------------------------------------------------- review queue


def create_review(
    conn: Connection, workspace_id: UUID, actor: str, a: UUID, b: UUID, *,
    confidence: str | None = None, evidence: str | None = None, notes: str | None = None,
) -> UUID:
    if a == b:
        raise ValueError("same_person")
    for pid in (a, b):
        if people.get_person(conn, pid, include_protected=True) is None:
            raise ValueError("person_not_found")
    x, y = _ordered(a, b)
    rid = conn.execute(
        text(
            "INSERT INTO person_duplicate_review(workspace_id, person_a_id, person_b_id, confidence, evidence, notes) "
            "VALUES (:w, :a, :b, :c, :ev, :n) RETURNING id"
        ),
        {"w": workspace_id, "a": x, "b": y, "c": confidence, "ev": evidence, "n": notes},
    ).scalar_one()
    audit.write_audit(conn, workspace_id, actor, "person.review.create", entity="person_duplicate_review",
                      entity_id=str(rid), after={"person_a_id": str(x), "person_b_id": str(y)})
    return rid


def list_reviews(conn: Connection, *, status: str | None = None) -> list[dict[str, Any]]:
    sql = ("SELECT id, person_a_id, person_b_id, status, confidence, evidence, notes, decided_by, "
           "decided_at, created_at FROM person_duplicate_review")
    params = {}
    if status is not None:
        sql += " WHERE status = :st"
        params["st"] = status
    sql += " ORDER BY created_at DESC"
    return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]


def decide_review(
    conn: Connection, workspace_id: UUID, actor: str, review_id: UUID, *, decision: str,
    canonical_person_id: UUID | None = None, reason: str | None = None, evidence: str | None = None,
) -> dict[str, Any]:
    """Resolve a review: ``merge`` (requires which record is canonical), ``distinct`` (assert
    definitely different), ``defer`` (keep pending research) or ``reject`` (not a duplicate)."""
    row = conn.execute(
        text("SELECT id, person_a_id, person_b_id, status FROM person_duplicate_review WHERE id = :id"),
        {"id": review_id},
    ).mappings().first()
    if row is None:
        raise ValueError("review_not_found")
    if row["status"] not in ("pending", "deferred"):
        raise ValueError("review_already_decided")
    a, b = row["person_a_id"], row["person_b_id"]
    result: dict[str, Any] = {"review_id": str(review_id)}

    if decision == "merge":
        if canonical_person_id not in (a, b):
            raise ValueError("canonical_must_be_one_of_the_pair")
        merged = b if canonical_person_id == a else a
        result["merge"] = merge_people(conn, workspace_id, actor, canonical_person_id, merged,
                                       reason=reason, evidence=evidence)
        new_status = "merged"
    elif decision == "distinct":
        result["assertion_id"] = str(assert_distinct(conn, workspace_id, actor, a, b, reason=reason, evidence=evidence))
        new_status = "distinct"
    elif decision == "defer":
        new_status = "deferred"
    elif decision == "reject":
        new_status = "rejected"
    else:
        raise ValueError("invalid_decision")

    conn.execute(
        text("UPDATE person_duplicate_review SET status = :st, decided_by = :by, decided_at = now() WHERE id = :id"),
        {"st": new_status, "by": actor, "id": review_id},
    )
    audit.write_audit(conn, workspace_id, actor, "person.review.decide", entity="person_duplicate_review",
                      entity_id=str(review_id), after={"decision": decision, "status": new_status})
    result["status"] = new_status
    return result
