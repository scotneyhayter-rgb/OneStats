"""Phase 10, Stages 10.3/10.4 — archive connectors (interface-only) + historical alias recognition.

Aliases broaden search without rewriting source text; archive providers are registered interface-only
(never claimed operational). Alias tests rolled back; skipped without a live DB. Connector test needs no DB.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain.autosync.connectors import STATUS_INTERFACE_ONLY, catalog
from onestats.domain.research import aliases

settings = get_settings()


def test_archive_connectors_are_interface_only():
    described = {c["connector_id"]: c for c in catalog.describe()}
    for cid in ("trove", "newspaper_archive", "library_collection"):
        assert cid in described, cid
        assert described[cid]["status"] == STATUS_INTERFACE_ONLY   # not operational until verified access


dbmark = pytest.mark.skipif(not settings.db_configured, reason="no live database credential configured")
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


def _ws(conn, name):
    wid = conn.execute(text("INSERT INTO workspace(name, type) VALUES (:n,'club') RETURNING id"), {"n": name}).scalar_one()
    conn.execute(text("INSERT INTO app_user(id, username) VALUES (:a, :u) ON CONFLICT (id) DO NOTHING"),
                 {"a": ACTOR, "u": f"actor-{name}"})
    set_workspace(conn, wid)
    return wid


@dbmark
def test_alias_expansion_includes_variants(conn):
    wid = _ws(conn, "ALIAS")
    club = uuid.uuid4()
    aliases.register_alias(conn, wid, ACTOR, entity_type="club", entity_id=club, alias="Rhymney CC",
                           alias_kind="former_name")
    aliases.register_alias(conn, wid, ACTOR, entity_type="club", entity_id=club, alias="Rhymney Cricket Club")
    aliases.register_alias(conn, wid, ACTOR, entity_type="club", entity_id=club, alias="Rymney CC",
                           alias_kind="transcription")   # a newspaper misspelling
    expanded = aliases.expand_terms(conn, wid, "Rhymney CC")
    assert set(expanded) >= {"Rhymney CC", "Rhymney Cricket Club", "Rymney CC"}
    # an unrelated term is not expanded
    assert aliases.expand_terms(conn, wid, "Moyston") == ["Moyston"]


@dbmark
def test_alias_validation(conn):
    wid = _ws(conn, "ALIAS VAL")
    with pytest.raises(ValueError, match="invalid_entity_type"):
        aliases.register_alias(conn, wid, ACTOR, entity_type="spaceship", alias="x")
    with pytest.raises(ValueError, match="alias_required"):
        aliases.register_alias(conn, wid, ACTOR, entity_type="club", alias="  ")
