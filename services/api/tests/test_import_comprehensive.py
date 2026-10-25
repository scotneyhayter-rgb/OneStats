"""Phase 8, Stage 8.10 — comprehensive coverage gaps.

Fills the remaining STEP 12 scenarios not already covered elsewhere: malformed files are handled
gracefully, any adapter (not just CSV) imports end-to-end through the one pipeline, and a sparse file
with missing fields imports with the gaps left unknown. Rolled back; the pure checks need no DB.
"""
from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain.importing import detect_adapter, pipeline
from onestats.domain.importing.adapters.csv_scorecard import CsvScorecardAdapter
from onestats.domain.importing.adapters.json_generic import JsonGenericAdapter
from onestats.domain.importing.adapters.xml_generic import XmlGenericAdapter

settings = get_settings()
ACTOR = "11111111-1111-1111-1111-111111111111"


# ---- malformed / unrecognised (no DB) -------------------------------------------------------------

def test_garbage_is_not_recognised_by_any_adapter():
    assert detect_adapter("%%% not a known format %%%", "junk.dat") is None
    assert detect_adapter("", "empty.csv") is None


def test_malformed_json_raises_cleanly():
    with pytest.raises(json.JSONDecodeError):
        JsonGenericAdapter().parse("[ {not valid json ")


def test_malformed_xml_raises_value_error():
    with pytest.raises((ValueError,)):
        XmlGenericAdapter().parse("<matches><match></matches>")   # unclosed tag


def test_missing_optional_fields_leave_gaps_unknown():
    # only the essentials present — no result/grade/venue columns
    csv = "Date,HomeTeam,AwayTeam\n2024-01-06,Alpha CC,Beta CC\n"
    ds = CsvScorecardAdapter().normalize(CsvScorecardAdapter().parse(csv))
    m = ds.matches[0]
    assert m.result_type is None and m.result_status == "unresolved"
    assert m.grade_ref is None and m.venue_ref is None     # absent → unknown, not invented
    assert len(ds.teams) == 2


# ---- any adapter imports end-to-end (DB) ----------------------------------------------------------

pytestmark_db = pytest.mark.skipif(not settings.db_configured, reason="no live database credential configured")


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


@pytestmark_db
def test_json_adapter_imports_end_to_end(conn):
    wid = _ws(conn, "COMP JSON")
    rows = [{"Date": "2024-01-06", "HomeTeam": "Alpha CC", "AwayTeam": "Beta CC", "Result": "Home win"}]
    adapter = JsonGenericAdapter()
    ds = adapter.normalize(adapter.parse(json.dumps(rows)))
    out = pipeline.import_dataset(conn, wid, ACTOR, dataset=ds, commit=True)
    assert out["created"]["match"] == 1 and out["source_system"] == "generic_json"
    assert conn.execute(text("SELECT count(*) FROM match WHERE source_system='generic_json'")).scalar_one() == 1


@pytestmark_db
def test_xml_adapter_imports_end_to_end(conn):
    wid = _ws(conn, "COMP XML")
    xml = ('<matches><match Date="2024-01-06" HomeTeam="Alpha CC" AwayTeam="Beta CC" Result="Home win"/>'
           '<match Date="2024-01-13" HomeTeam="Beta CC" AwayTeam="Alpha CC" Result="Away win"/></matches>')
    ds = XmlGenericAdapter().normalize(XmlGenericAdapter().parse(xml))
    out = pipeline.import_dataset(conn, wid, ACTOR, dataset=ds, commit=True)
    assert out["created"]["match"] == 2 and out["source_system"] == "generic_xml"
    # drafts, workspace-scoped
    assert conn.execute(text("SELECT count(*) FROM match WHERE approval_status='draft'")).scalar_one() == 2
