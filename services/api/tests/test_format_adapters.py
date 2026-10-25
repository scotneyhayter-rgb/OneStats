"""Phase 8, Stage 8.4 — Excel, JSON and XML adapters (shared tabular builder).

Pure logic (no database). Each adapter detects its format, parses to rows and produces the same
Canonical model as the CSV adapter for the same data; detection routes each file to the right adapter
(and a CricketStatz export is never misrouted to the generic JSON adapter); and XML parsing rejects
unsafe documents (entity-expansion / XXE) via defusedxml.
"""
from __future__ import annotations

import io
import json
from datetime import date

import pytest

from onestats.domain.importing import detect_adapter
from onestats.domain.importing.adapters.csv_scorecard import CsvScorecardAdapter
from onestats.domain.importing.adapters.excel_scorecard import ExcelScorecardAdapter
from onestats.domain.importing.adapters.json_generic import JsonGenericAdapter
from onestats.domain.importing.adapters.xml_generic import XmlGenericAdapter

HEADER = ["Date", "HomeTeam", "AwayTeam", "Competition", "Grade", "Venue", "Result", "Format", "Round"]
ROWS = [
    ["2024-01-06", "Alpha CC", "Beta CC", "Saturday League", "A Grade", "Alpha Oval", "Home win", "One-day", "1"],
    ["2024-01-13", "Beta CC", "Alpha CC", "Saturday League", "A Grade", "Beta Park", "Away win", "One-day", "2"],
]
CSV = "\n".join([",".join(HEADER)] + [",".join(r) for r in ROWS]) + "\n"
JSON_ARR = json.dumps([dict(zip(HEADER, r)) for r in ROWS])
XML = (
    "<matches>"
    + "".join(f'<match Date="{r[0]}" HomeTeam="{r[1]}" AwayTeam="{r[2]}" Competition="{r[3]}" '
              f'Grade="{r[4]}" Venue="{r[5]}" Result="{r[6]}" Format="{r[7]}" Round="{r[8]}"/>' for r in ROWS)
    + "</matches>"
)


def _xlsx_bytes() -> bytes:
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(HEADER)
    for r in ROWS:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _summary(ds):
    return ({t.source_ref for t in ds.teams}, len(ds.matches),
            ds.matches[0].result_type, str(ds.matches[0].match_date))


def test_all_formats_produce_the_same_canonical_model():
    csv_ds = CsvScorecardAdapter().normalize(CsvScorecardAdapter().parse(CSV))
    xlsx = _xlsx_bytes()
    excel_ds = ExcelScorecardAdapter().normalize(ExcelScorecardAdapter().parse(xlsx))
    json_ds = JsonGenericAdapter().normalize(JsonGenericAdapter().parse(JSON_ARR))
    xml_ds = XmlGenericAdapter().normalize(XmlGenericAdapter().parse(XML))
    expected = ({"alpha-cc", "beta-cc"}, 2, "home_win", "2024-01-06")
    assert _summary(csv_ds) == expected
    assert _summary(excel_ds) == expected
    assert _summary(json_ds) == expected
    assert _summary(xml_ds) == expected


def test_xml_child_element_form_also_parses():
    doc = ("<matches><match><Date>2024-01-06</Date><HomeTeam>Alpha CC</HomeTeam>"
           "<AwayTeam>Beta CC</AwayTeam><Result>Home win</Result></match></matches>")
    ds = XmlGenericAdapter().normalize(XmlGenericAdapter().parse(doc))
    assert len(ds.matches) == 1 and ds.matches[0].match_date == date(2024, 1, 6)
    assert ds.matches[0].result_type == "home_win"


def test_detection_routes_each_format_correctly():
    assert detect_adapter(CSV, "f.csv").format_id == "csv_scorecard"
    assert detect_adapter(_xlsx_bytes(), "f.xlsx").format_id == "excel_scorecard"
    assert detect_adapter(JSON_ARR, "f.json").format_id == "generic_json"
    assert detect_adapter(XML, "f.xml").format_id == "generic_xml"
    # a CricketStatz export (a JSON object with MatchID) must NOT route to the generic JSON adapter
    cs = '{"matches":[{"MatchID":1,"HomeTeam":1}],"players":[],"teams":[]}'
    assert JsonGenericAdapter().detect(cs) == 0.0
    assert detect_adapter(cs, "export.json").format_id == "cricket_statz"


def test_json_rejects_non_array():
    with pytest.raises(ValueError, match="array of match objects"):
        JsonGenericAdapter().parse('{"not":"an array"}')


def test_xml_rejects_entity_expansion_attack():
    # a classic billion-laughs; defusedxml must refuse it rather than expand
    evil = ('<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">'
            '<!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;">]><matches>&lol2;</matches>')
    with pytest.raises(ValueError, match="unsafe XML"):
        XmlGenericAdapter().parse(evil)
