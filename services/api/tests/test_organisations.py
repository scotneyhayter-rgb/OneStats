"""Live organisation & historical-identity tests (Phase 4, Stage 1).

Rolled back in a single transaction (no data persists); skipped automatically when no live
database credential is configured. Everything runs as the least-privilege ``onestats_app``
role under FORCE RLS, so workspace isolation is exercised for real.

Covers the twelve Stage 1 verification points: creation/update, historical name changes,
period-correct name resolution, source-identity preservation, duplicate detection, confirmed
merge, merge reversal, distinct-identity assertions, workspace isolation, permission
enforcement, audit logging, and invalid/conflicting inputs.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import organisations, permissions

settings = get_settings()
pytestmark = pytest.mark.skipif(
    not settings.db_configured, reason="no live database credential configured"
)

ACTOR = "11111111-1111-1111-1111-111111111111"


@pytest.fixture
def conn():
    eng = create_engine(settings.database_url, future=True)
    with eng.connect() as c:
        trans = c.begin()
        try:
            yield c
        finally:
            trans.rollback()
    eng.dispose()


def _mk_workspace(conn, name):
    return conn.execute(
        text("INSERT INTO workspace(name, type) VALUES (:n,'club') RETURNING id"), {"n": name}
    ).scalar_one()


def _mk_user(conn, username):
    return conn.execute(
        text("INSERT INTO app_user(username) VALUES (:u) RETURNING id"), {"u": username}
    ).scalar_one()


def _ws_with_context(conn, name):
    wid = _mk_workspace(conn, name)
    set_workspace(conn, wid)
    return wid


# 1. creation + update ------------------------------------------------------


def test_create_and_update_organisation(conn):
    wid = _ws_with_context(conn, "ORG WS1")
    oid = organisations.create_organisation(
        conn, wid, ACTOR, name="Ararat Cricket Club", kind="club", short_name="Ararat"
    )
    org = organisations.get_organisation(conn, oid)
    assert org["name"] == "Ararat Cricket Club"
    assert org["kind"] == "club"
    assert org["status"] == "active"
    assert org["merged_into_id"] is None

    updated = organisations.update_organisation(
        conn, wid, ACTOR, oid, short_name="ACC", notes="Ballarat region"
    )
    assert updated["short_name"] == "ACC"
    assert updated["notes"] == "Ballarat region"


# 2 + 3. historical name changes + period-correct resolution ----------------


def test_name_history_and_period_correct_resolution(conn):
    wid = _ws_with_context(conn, "ORG WS2")
    oid = organisations.create_organisation(conn, wid, ACTOR, name="Rhymney/Moyston CC")
    # Earlier recorded names with effective ranges.
    organisations.add_name_history(
        conn, wid, ACTOR, oid, name="Moyston CC", valid_from=date(1900, 1, 1), valid_to=date(1979, 12, 31)
    )
    organisations.add_name_history(
        conn, wid, ACTOR, oid, name="Rhymney/Moyston Cricket Club", valid_from=date(1980, 1, 1)
    )
    assert organisations.name_as_of(conn, oid, date(1950, 6, 1)) == "Moyston CC"
    assert organisations.name_as_of(conn, oid, date(1995, 6, 1)) == "Rhymney/Moyston Cricket Club"
    # A renaming through update_organisation is preserved in history.
    organisations.update_organisation(
        conn, wid, ACTOR, oid, name="Rhymney/Moyston CC (current)", name_change_note="2024 rebrand"
    )
    history = organisations.list_name_history(conn, oid)
    assert any(h["name"] == "Rhymney/Moyston CC (current)" for h in history)


# 4. source-identity preservation + idempotent re-import --------------------


def test_source_identity_preserved_and_idempotent(conn):
    wid = _ws_with_context(conn, "ORG WS3")
    oid = organisations.create_organisation(
        conn, wid, ACTOR, name="Imported Club", source_system="cricket_statz", source_ref="CS-42"
    )
    ids = organisations.list_source_identities(conn, oid)
    assert len(ids) == 1 and ids[0]["source_ref"] == "CS-42"

    # Re-importing the same source reference must NOT create a duplicate.
    again = organisations.add_source_identity(
        conn, wid, ACTOR, oid, source_system="cricket_statz", source_ref="CS-42"
    )
    assert again["created"] is False
    assert len(organisations.list_source_identities(conn, oid)) == 1


# 5. duplicate detection (never auto-merge) ---------------------------------


def test_duplicate_candidates_are_suggested_not_merged(conn):
    wid = _ws_with_context(conn, "ORG WS4")
    a = organisations.create_organisation(conn, wid, ACTOR, name="Ararat CC")
    b = organisations.create_organisation(conn, wid, ACTOR, name="ararat   cc")  # same normalised name
    cands = organisations.find_duplicate_candidates(conn, a)
    assert any(c["organisation_id"] == b for c in cands)
    # Still two independent, un-merged records: suggestion only.
    assert organisations.get_organisation(conn, a)["merged_into_id"] is None
    assert organisations.get_organisation(conn, b)["merged_into_id"] is None


def test_distinct_named_historical_identities_are_not_duplicates(conn):
    """Rhymney CC, Moyston CC and Rhymney/Moyston CC coexist as distinct records."""
    wid = _ws_with_context(conn, "ORG WS5")
    rhymney = organisations.create_organisation(conn, wid, ACTOR, name="Rhymney CC", is_historical=True)
    moyston = organisations.create_organisation(conn, wid, ACTOR, name="Moyston CC", is_historical=True)
    combined = organisations.create_organisation(conn, wid, ACTOR, name="Rhymney/Moyston CC")
    # Different names → none flagged as a duplicate of another.
    assert organisations.find_duplicate_candidates(conn, rhymney) == []
    assert organisations.find_duplicate_candidates(conn, moyston) == []
    assert organisations.find_duplicate_candidates(conn, combined) == []
    all_orgs = {o["id"] for o in organisations.list_organisations(conn)}
    assert {rhymney, moyston, combined} <= all_orgs


# 6 + 7. confirmed merge + reversal -----------------------------------------


def test_merge_is_reversible_and_preserves_records(conn):
    wid = _ws_with_context(conn, "ORG WS6")
    canonical = organisations.create_organisation(conn, wid, ACTOR, name="Keep Club")
    dup = organisations.create_organisation(
        conn, wid, ACTOR, name="Dup Club", source_system="cs", source_ref="DUP-1"
    )
    result = organisations.merge_organisations(conn, wid, ACTOR, canonical, dup, reason="confirmed dupe")

    merged = organisations.get_organisation(conn, dup)
    assert merged["merged_into_id"] == canonical
    assert merged["status"] == "merged"
    # The merged record is NOT deleted; its source identity survives.
    assert len(organisations.list_source_identities(conn, dup)) == 1
    assert organisations.resolve_canonical(conn, dup) == canonical
    # Default listing hides merged records; include_merged surfaces them.
    assert dup not in {o["id"] for o in organisations.list_organisations(conn)}
    assert dup in {o["id"] for o in organisations.list_organisations(conn, include_merged=True)}

    # Reverse it.
    organisations.undo_merge(conn, wid, ACTOR, result["merge_id"])
    reinstated = organisations.get_organisation(conn, dup)
    assert reinstated["merged_into_id"] is None
    assert reinstated["status"] == "active"


def test_undo_merge_twice_rejected(conn):
    wid = _ws_with_context(conn, "ORG WS6b")
    c = organisations.create_organisation(conn, wid, ACTOR, name="C")
    d = organisations.create_organisation(conn, wid, ACTOR, name="D")
    res = organisations.merge_organisations(conn, wid, ACTOR, c, d)
    organisations.undo_merge(conn, wid, ACTOR, res["merge_id"])
    with pytest.raises(ValueError, match="already_undone"):
        organisations.undo_merge(conn, wid, ACTOR, res["merge_id"])


# 8. distinct-identity assertions -------------------------------------------


def test_distinct_assertion_blocks_merge(conn):
    wid = _ws_with_context(conn, "ORG WS7")
    rhymney = organisations.create_organisation(conn, wid, ACTOR, name="Rhymney CC")
    moyston = organisations.create_organisation(conn, wid, ACTOR, name="Moyston CC")
    organisations.assert_distinct(conn, wid, ACTOR, rhymney, moyston, reason="separate clubs")
    assert organisations.are_asserted_distinct(conn, rhymney, moyston)
    # Order must not matter.
    assert organisations.are_asserted_distinct(conn, moyston, rhymney)
    with pytest.raises(ValueError, match="asserted_distinct"):
        organisations.merge_organisations(conn, wid, ACTOR, rhymney, moyston)


def test_assertion_removes_from_duplicate_candidates(conn):
    wid = _ws_with_context(conn, "ORG WS7b")
    a = organisations.create_organisation(conn, wid, ACTOR, name="Same Name CC")
    b = organisations.create_organisation(conn, wid, ACTOR, name="Same Name CC")
    assert any(c["organisation_id"] == b for c in organisations.find_duplicate_candidates(conn, a))
    organisations.assert_distinct(conn, wid, ACTOR, a, b, reason="different towns")
    assert all(c["organisation_id"] != b for c in organisations.find_duplicate_candidates(conn, a))


# 9. workspace isolation (incl. no cross-workspace merge) -------------------


def test_cross_workspace_merge_is_impossible(conn):
    wid_a = _mk_workspace(conn, "ISO ORG A")
    wid_b = _mk_workspace(conn, "ISO ORG B")
    set_workspace(conn, wid_a)
    org_a = organisations.create_organisation(conn, wid_a, ACTOR, name="A Club")
    set_workspace(conn, wid_b)
    org_b = organisations.create_organisation(conn, wid_b, ACTOR, name="B Club")

    # Operating in workspace A, workspace B's org is invisible...
    set_workspace(conn, wid_a)
    assert org_b not in {o["id"] for o in organisations.list_organisations(conn)}
    assert organisations.get_organisation(conn, org_b) is None
    # ...so a cross-workspace merge cannot even be formed.
    with pytest.raises(ValueError, match="organisation_not_found"):
        organisations.merge_organisations(conn, wid_a, ACTOR, org_a, org_b)


def test_organisation_rows_isolated_by_workspace(conn):
    wid_a = _mk_workspace(conn, "ISO ORG A2")
    wid_b = _mk_workspace(conn, "ISO ORG B2")
    set_workspace(conn, wid_a)
    organisations.create_organisation(conn, wid_a, ACTOR, name="Only In A")
    set_workspace(conn, wid_b)
    assert organisations.list_organisations(conn) == []


# 10. role-based permission enforcement -------------------------------------


def test_organisation_manage_permission_matrix(conn):
    wid = _ws_with_context(conn, "ORG PERM WS")
    admin = _mk_user(conn, "org_admin")
    viewer = _mk_user(conn, "org_viewer")
    permissions.grant_role(conn, admin, wid, "workspace_admin")
    permissions.grant_role(conn, viewer, wid, "viewer")
    assert "organisation.manage" in permissions.effective_permissions(conn, admin, wid, False)
    assert "organisation.manage" not in permissions.effective_permissions(conn, viewer, wid, False)
    # Super Administrator holds it everywhere.
    assert permissions.has_permission(conn, admin, wid, True, "organisation.manage")


# 11. audit logging ----------------------------------------------------------


def test_sensitive_actions_are_audited(conn):
    wid = _ws_with_context(conn, "ORG AUDIT WS")
    a = organisations.create_organisation(conn, wid, ACTOR, name="Audit A")
    b = organisations.create_organisation(conn, wid, ACTOR, name="Audit B")
    res = organisations.merge_organisations(conn, wid, ACTOR, a, b, reason="dupe")
    organisations.undo_merge(conn, wid, ACTOR, res["merge_id"])
    organisations.assert_distinct(conn, wid, ACTOR, a, b, reason="actually distinct")
    actions = conn.execute(
        text("SELECT action FROM audit_log WHERE action LIKE 'organisation%'")
    ).scalars().all()
    for expected in ("organisation.create", "organisation.merge", "organisation.merge.undo",
                     "organisation.assert_distinct"):
        assert expected in actions


# 12. invalid / conflicting inputs ------------------------------------------


def test_invalid_inputs_rejected(conn):
    wid = _ws_with_context(conn, "ORG INVALID WS")
    with pytest.raises(ValueError, match="missing_name"):
        organisations.create_organisation(conn, wid, ACTOR, name="   ")
    with pytest.raises(ValueError, match="invalid_kind"):
        organisations.create_organisation(conn, wid, ACTOR, name="Ok", kind="banana")
    oid = organisations.create_organisation(conn, wid, ACTOR, name="Solo")
    with pytest.raises(ValueError, match="cannot_merge_same"):
        organisations.merge_organisations(conn, wid, ACTOR, oid, oid)
    with pytest.raises(ValueError, match="same_organisation"):
        organisations.assert_distinct(conn, wid, ACTOR, oid, oid)


def test_cannot_merge_an_already_merged_record(conn):
    wid = _ws_with_context(conn, "ORG CONFLICT WS")
    a = organisations.create_organisation(conn, wid, ACTOR, name="A1")
    b = organisations.create_organisation(conn, wid, ACTOR, name="B1")
    c = organisations.create_organisation(conn, wid, ACTOR, name="C1")
    organisations.merge_organisations(conn, wid, ACTOR, a, b)
    with pytest.raises(ValueError, match="already_merged"):
        organisations.merge_organisations(conn, wid, ACTOR, c, b)


# per-club logo: store → attach → read back → remove -------------------------


def _png_bytes(size=(16, 16)) -> bytes:
    import io

    from PIL import Image

    im = Image.new("RGBA", size, (12, 34, 56, 255))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def test_organisation_logo_store_attach_and_remove(conn, tmp_path):
    from onestats.domain import logos

    wid = _ws_with_context(conn, "ORG LOGO WS")
    oid = organisations.create_organisation(conn, wid, ACTOR, name="Buangor CC", kind="club")
    assert organisations.get_organisation(conn, oid)["logo_ref"] is None   # additive default

    cfg = settings.model_copy(update={"media_root": str(tmp_path)})
    stored = logos.store_logo(cfg, wid, _png_bytes(), "image/png")
    organisations.set_logo(conn, oid, stored["logo_ref"])

    org = organisations.get_organisation(conn, oid)
    assert org["logo_ref"] == stored["logo_ref"]
    path = logos.logo_path(cfg, wid, org["logo_ref"])
    assert path is not None and path.exists()                               # bytes actually on disk

    # removing clears the reference and the file
    organisations.set_logo(conn, oid, None)
    logos.remove_logo(cfg, wid, stored["logo_ref"])
    assert organisations.get_organisation(conn, oid)["logo_ref"] is None
    assert logos.logo_path(cfg, wid, stored["logo_ref"]) is None
